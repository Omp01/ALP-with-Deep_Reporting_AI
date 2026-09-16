# Grounded AI Reporting & Citation Verification System

## Executive Overview

The **Reporting & Insight Engine** (`services/reporting-engine`) operates as an independent microservice on port `8002`. Unlike conventional AI reporting systems that generate unverified text, this system enforces **100% evidence-grounded insights with verifiable citations**.

---

## The Grounding Guarantee

```
+-----------------------------------------------------------------------+
|                PostgreSQL Relational / Telemetry Store                |
|  - learning_events: question attempts, accuracy, latencies            |
|  - learner_competencies: live mastery scores, confidence, trends      |
|  - learner_risks: multi-signal early warning flags                    |
+-----------------------------------------------------------------------+
                                   |
                                   v
+-----------------------------------------------------------------------+
|                    Evidence Package Builder                           |
|  Extracts atomic, immutable facts & indexes them as [E-1], [E-2], ... |
+-----------------------------------------------------------------------+
                                   |
                                   v
+-----------------------------------------------------------------------+
|                  AI Synthesis (Constrained Prompt)                     |
|  LLM instructed: "Every single claim MUST reference an [E-#] key"    |
+-----------------------------------------------------------------------+
                                   |
                                   v
+-----------------------------------------------------------------------+
|                    Citation & Grounding Validator                     |
|  - Verifies cited keys against the evidence package                   |
|  - Rejects/penalizes unsupported claims                               |
|  - Calculates Grounding Confidence Score (0.0 – 1.0)                  |
+-----------------------------------------------------------------------+
                                   |
                                   v
+-----------------------------------------------------------------------+
|                     Persistent Insight Card                           |
|  Saved in ai_insights table with structured citation array            |
+-----------------------------------------------------------------------+
```

---

## Citation Schema & Format

Every generated claim embeds an explicit bracketed citation:
```
"Evaluation confirms: Mastery in React State Management is 0.42 (status: novice, confidence: 0.95) [E-1]."
```

### Citation Object Data Model:
```json
{
  "citation_key": "E-1",
  "source_type": "competency_mastery",
  "source_id": "7662c648-9366-4e50-a10c-99d7a22ef72f",
  "snippet": "Mastery in React State Management is 0.42 (status: novice, confidence: 0.95)",
  "confidence": 0.95
}
```

---

## Reporting Endpoints & Multi-Surface Analytics

| Endpoint | Target Surface | Purpose |
| :--- | :--- | :--- |
| `POST /api/v1/insights/generate` | All surfaces | Generates grounded narrative with citations |
| `GET /api/v1/insights/{id}` | All surfaces | Retrieve saved insight narrative and citations |
| `GET /api/v1/insights/{id}/evidence` | Audit modal | Inspect raw backing facts and data points |
| `GET /api/v1/analytics/learner/{id}` | Learner Dashboard | Real-time accuracy, latency, mastery distribution |
| `GET /api/v1/analytics/team/{id}` | Manager Dashboard | Cohort completion rate, skill gaps, risk overview |
| `GET /api/v1/analytics/organization` | Admin Dashboard | High-level executive KPIs and mastery index |
| `POST /api/v1/reports/digest/generate` | Scheduled Reports | On-demand or scheduled proactive digest |
| `GET /api/v1/reports/digest/latest` | Email / Push UI | Most recent proactive intelligence report |
| `GET /api/v1/export/{events,competencies,risks}` | BI Warehouses | CSV and JSON streaming exports |
| `GET /api/v1/embed/report` | External Portals | Embeddable responsive HTML/JSON widget |
