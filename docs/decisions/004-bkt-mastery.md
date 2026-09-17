# ADR-004: Bayesian Knowledge Tracing (BKT) Mastery Engine

## Status
Accepted

## Context
The Adaptive LMS requires an explainable, probabilistic model to track each learner's mastery state for individual competencies in real time as they interact with content (videos, reading modules, quizzes, coding assignments). 

Previous iterations considered either heuristic weighted rules or deep neural knowledge tracing (DKT). 
- Heuristic weighted averages lack a rigorous probabilistic foundation.
- Deep Neural Knowledge Tracing (DKT / RNNs) are "black-box" models where teachers and managers cannot easily audit why an adaptive path branched or why a student was flagged for remediation.

## Decision
We implemented the classical **Corbett & Anderson Bayesian Knowledge Tracing (BKT)** model.

The model tracks the probability $P(L_t)$ that a student knows a skill at time step $t$, parameterized by:
1. $P(L_0)$: Initial probability of mastery (prior)
2. $P(T)$: Probability of learning the skill during a transition step
3. $P(G)$: Probability of a correct guess despite not knowing the skill
4. $P(S)$: Probability of a slip (mistake) despite knowing the skill

The posterior update given observation $obs \in \{0, 1\}$ is computed as:
$$P(L_t \mid \text{obs}=1) = \frac{P(L_{t-1}) \cdot (1 - P(S))}{P(L_{t-1}) \cdot (1 - P(S)) + (1 - P(L_{t-1})) \cdot P(G)}$$
$$P(L_t \mid \text{obs}=0) = \frac{P(L_{t-1}) \cdot P(S)}{P(L_{t-1}) \cdot P(S) + (1 - P(L_{t-1})) \cdot (1 - P(G))}$$

And the state transition to step $t+1$:
$$P(L_{t+1}) = P(L_t \mid \text{obs}) + (1 - P(L_t \mid \text{obs})) \cdot P(T)$$

## Consequences
- **Auditability:** Every update produces an explicit posterior probability saved into `competency_history`.
- **Explainability:** Pedagogical decisions (`advance`, `remediate`, `change_modality`, `skip`, `revisit`) cite the exact $P(L_t)$ value and confidence intervals.
- **Low Latency:** Calculations take < 1ms per event in memory, ensuring fast real-time next-step recommendations.
