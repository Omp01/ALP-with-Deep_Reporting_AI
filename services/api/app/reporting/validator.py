"""
Citation validation (spec sections 28-29). Runs on every claim before a report is shown.

A claim is accepted only if:
  1. it cites at least one evidence id, and it has a valid claim type;
  2. every cited id exists in the evidence package of this report (so it cannot be invented);
  3. every cited record belongs to the report's tenant (records are stored with their org id and checked, not trusted);
  4. every cited record belongs to the report's scope and period (a record with a time must fall inside the period; a learner report
     cannot cite another learner's records);
  5. every number in the claim text equals a value in the cited metrics or cited records (as itself, as a percentage, or rounded);
  6. it does not assert causation: a CAUSAL_CLAIM is rejected (the platform has no causal evidence), and causal wording in an
     observation or correlation is flagged and the claim is rejected too, because the wording overclaims.

Statuses: `accepted`, `rejected`. `flags` lists what was found either way. Rejected claims are kept with their reasons so a person
can see what the model tried to say.
"""

import re
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Set

from app.reporting.package import CLAIM_TYPES

CAUSAL_PATTERNS = [r"\bcaus(?:e|ed|es|ing)\b", r"\bled to\b", r"\bresult(?:ed|s)? in\b", r"\bbecause of\b", r"\bdue to\b", r"\bas a result of\b", r"\bis responsible for\b", r"\bimproved because\b"]
NUMBER = re.compile(r"(?<![\w.])[-+]?\d+(?:\.\d+)?%?")
NEGATION = re.compile(r"[^.]*(?:does not|do not|cannot|can not|not|no)\s+(?:establish|causal)[^.]*\.?", re.I)   # "does not establish that ... caused ..." is the right wording
ID_LIKE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-", re.I)


def _numbers_in(value: Any, out: Set[float]) -> None:
    if isinstance(value, bool) or value is None:
        return
    if isinstance(value, (int, float)):
        for v in (float(value), float(value) * 100 if -1.0 <= float(value) <= 1.0 else float(value)):
            out.add(round(v, 2))
            out.add(round(v, 1))
            out.add(round(v))
        out.add(round(abs(float(value)), 2))
    elif isinstance(value, dict):
        for v in value.values():
            _numbers_in(v, out)
    elif isinstance(value, (list, tuple)):
        out.add(float(len(value)))
        for v in value:
            _numbers_in(v, out)
    elif isinstance(value, str):
        for token in NUMBER.findall(value):
            try:
                out.add(round(float(token.rstrip("%")), 2))
            except ValueError:
                pass


def allowed_numbers(package: Dict[str, Any], claim: Dict[str, Any]) -> Set[float]:
    """Numbers the claim may state: values of the metrics and records it cites."""
    allowed: Set[float] = set()
    for mid in claim.get("metric_ids", []):
        m = package["metrics"].get(mid)
        if m:
            _numbers_in(m["value"], allowed)
            _numbers_in(m.get("definition"), allowed)        # thresholds stated in a metric's definition are stored facts too
            _numbers_in(m.get("name"), allowed)
    for eid in claim.get("evidence_ids", []):
        rec = package["records"].get(eid)
        if rec:
            _numbers_in(rec.get("data"), allowed)
    return allowed


def claim_numbers(text: str) -> List[float]:
    out = []
    for token in NUMBER.findall(ID_LIKE.sub("", text)):
        try:
            out.append(round(float(token.rstrip("%")), 2))
        except ValueError:
            pass
    return out


def _parse(ts: Optional[str]) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(ts) if ts else None
    except ValueError:
        return None


def validate_claim(claim: Dict[str, Any], package: Dict[str, Any], org_id: str, factual: bool = True) -> Dict[str, Any]:
    """Returns the claim with `status` ('accepted'|'rejected') and `flags` (reasons)."""
    scope = package["report_scope"]
    flags: List[str] = []
    text = str(claim.get("claim") or "").strip()
    ctype = str(claim.get("claim_type") or "").upper()
    evidence_ids = [str(e) for e in claim.get("evidence_ids", []) if e]
    metric_ids = [str(m) for m in claim.get("metric_ids", []) if m]
    checked = {**claim, "claim": text, "claim_type": ctype, "evidence_ids": evidence_ids, "metric_ids": metric_ids}

    if not text:
        flags.append("the claim has no text")
    if ctype not in CLAIM_TYPES:
        flags.append(f"unknown claim type '{ctype}'")
    if ctype == "CAUSAL_CLAIM":
        flags.append("a causal claim was made and the platform has no causal evidence to support it")
    if factual and not evidence_ids:
        flags.append("no evidence is cited")

    period_start, period_end = _parse(scope.get("period_start")), _parse(scope.get("period_end"))
    for eid in evidence_ids:
        rec = package["records"].get(eid)
        if rec is None:
            flags.append(f"evidence '{eid}' does not exist in this report's evidence")
            continue
        if rec.get("org_id") != org_id:
            flags.append(f"evidence '{eid}' belongs to another tenant")
        if scope["scope_type"] == "learner" and rec.get("learner_id") not in (None, scope["scope_id"]):
            flags.append(f"evidence '{eid}' belongs to a different learner than the report is about")
        when = _parse(rec.get("occurred_at"))
        if when and period_start and period_end and rec["type"] in ("evidence", "update", "decision", "session") and not (period_start <= when <= period_end):
            flags.append(f"evidence '{eid}' is outside the report period")
    for mid in metric_ids:
        if mid not in package["metrics"]:
            flags.append(f"metric '{mid}' does not exist in this report's evidence")

    if not any(f.startswith("evidence '") or f == "no evidence is cited" for f in flags):
        allowed = allowed_numbers(package, checked)
        unsupported = [n for n in claim_numbers(text) if n not in allowed and round(n) not in allowed]
        if unsupported:
            flags.append("the claim states numbers that are not in the cited evidence: " + ", ".join(f"{n:g}" for n in unsupported[:4]))
    scan = NEGATION.sub("", text)
    if ctype != "CAUSAL_CLAIM" and any(re.search(p, scan, re.I) for p in CAUSAL_PATTERNS):
        flags.append("the wording implies causation; use 'associated with', 'followed by' or 'coincided with'")

    checked["flags"] = flags
    checked["status"] = "rejected" if flags else "accepted"
    return checked


def validate_all(claims: Iterable[Dict[str, Any]], package: Dict[str, Any], org_id: str, factual: bool = True) -> Dict[str, List[Dict[str, Any]]]:
    accepted, rejected = [], []
    for c in claims:
        result = validate_claim(c, package, org_id, factual)
        (accepted if result["status"] == "accepted" else rejected).append(result)
    return {"accepted": accepted, "rejected": rejected}


def validate_narrative(text: str, package: Dict[str, Any]) -> List[str]:
    """A free-text summary is not a claim, but its numbers must exist somewhere in the package and it must not overclaim."""
    flags: List[str] = []
    allowed: Set[float] = set()
    for m in package["metrics"].values():
        _numbers_in(m["value"], allowed)
        _numbers_in(m.get("definition"), allowed)
    for r in package["records"].values():
        _numbers_in(r.get("data"), allowed)
        _numbers_in(r.get("label"), allowed)
    for p in package["patterns"]:
        _numbers_in(p["statement"], allowed)
    unsupported = [n for n in claim_numbers(text) if n not in allowed and round(n) not in allowed]
    if unsupported:
        flags.append("numbers that are not in the evidence: " + ", ".join(f"{n:g}" for n in unsupported[:4]))
    scan = NEGATION.sub("", text)
    if any(re.search(p, scan, re.I) for p in CAUSAL_PATTERNS):
        flags.append("causal wording")
    return flags
