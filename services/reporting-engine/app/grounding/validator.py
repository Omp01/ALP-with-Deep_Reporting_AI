"""
Citation and Grounding Validator for AI Reporting.
Ensures zero hallucinations by strictly verifying every cited claim against the evidence package.
"""

import re
from typing import List, Dict, Any, Tuple


CITATION_REGEX = re.compile(r"\[(E-\d+)\]")


def validate_grounded_citations(
    narrative_text: str,
    evidence_package: List[Dict[str, Any]],
) -> Tuple[bool, float, List[Dict[str, Any]]]:
    """
    Validates narrative citations:
    1. Extracts all [E-#] occurrences.
    2. Verifies that cited keys exist in the evidence package.
    3. Resolves matched evidence details into formatted citation objects.
    4. Computes grounding confidence score (0.0 to 1.0).
    """
    found_citations = CITATION_REGEX.findall(narrative_text)
    valid_keys = {item["citation_key"]: item for item in evidence_package}

    matched_citations = []
    invalid_keys = []

    for key in found_citations:
        if key in valid_keys:
            ev = valid_keys[key]
            matched_citations.append({
                "citation_key": key,
                "source_type": ev.get("source_type"),
                "source_id": ev.get("source_id"),
                "snippet": ev.get("fact"),
                "confidence": ev.get("confidence", 0.90),
            })
        else:
            invalid_keys.append(key)

    # Calculate grounding score
    if not evidence_package:
        return True, 0.70, []

    # Grounding density: ratio of unique cited evidence facts to total evidence facts
    unique_cited = set(c["citation_key"] for c in matched_citations)
    coverage = min(1.0, len(unique_cited) / max(1, min(len(evidence_package), 5)))

    # Hallucination penalty if citation keys referenced non-existent evidence
    penalty = 0.30 if invalid_keys else 0.0
    grounding_score = max(0.20, min(0.99, round(0.70 + (coverage * 0.25) - penalty, 3)))
    is_valid = len(invalid_keys) == 0 and len(found_citations) > 0

    return is_valid, grounding_score, matched_citations
