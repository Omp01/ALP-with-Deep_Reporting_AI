"""
Database Seeding Script for Adaptive LMS (Stage 2: 5 Real Production Courses).

Populates the database with:
- 2 Organizations (Acme Corporation, TechNova Systems)
- Multiple Users per organization across all 5 roles (system_admin, org_admin, instructor, manager, learner)
- Teams with manager assignments and learner memberships
- 15 Granular Competencies aligned with Bloom's Taxonomy
- 5 Real Comprehensive Courses:
  1. Python Fundamentals (PY-FUND-101)
  2. SQL for Data Analytics (SQL-ANALYTICS-201)
  3. Data Engineering Fundamentals (DE-PIPELINES-301)
  4. Machine Learning Fundamentals (ML-CORE-401)
  5. AI & Generative AI Fundamentals (GENAI-LLM-501)
- Modules containing all 4 Modalities: VIDEO, ARTICLE, QUIZ, ASSIGNMENT
- Psychometric Assessment Items tagged with difficulty, discrimination, and error taxonomy
- Initial Enrollments

Run via:
    python scripts/seed.py
    or: docker exec alms-api python scripts/seed.py
"""

import sys
import os
import uuid
from datetime import datetime, timedelta

# Ensure python path includes services/api and shared
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, BASE_DIR)
sys.path.insert(0, os.path.join(BASE_DIR, "services", "api"))

from app.core.security import hash_password
from app.core.database import SessionLocal
from app.core.rbac import normalize_role
from app.services.skill_graph import topological_levels
from app.models import (
    CompetencyPrerequisite,
    RoleDefinition,
    UserRole,
    Organization,
    User,
    Team,
    UserTeam,
    Course,
    Module,
    ContentItem,
    ContentChunk,
    Assignment,
    Competency,
    CourseCompetency,
    ModuleCompetency,
    AssessmentItem,
    Enrollment,
    Quiz,
    QuizQuestion,
    QuizOption,
    QuizAttempt,
    QuestionResponse,
    ContentProgress,
    ContentCompetency,
    AdaptiveDecision,
)

DEFAULT_PASSWORD_HASH = hash_password("Password123!")


def reading_seconds(text: str) -> int:
    """Estimated reading time at 200 words per minute, in seconds (a stated estimate, not a measurement)."""
    return max(60, round(len(text.split()) / 200 * 60))

# Bloom's taxonomy level -> default competency difficulty (mirrors migration 003).
BLOOM_DIFFICULTY = {
    "remember": 0.10, "understand": 0.25, "apply": 0.50,
    "analyze": 0.65, "evaluate": 0.80, "create": 0.90,
}

# The demo curriculum's skill graph: (competency, prerequisite, min_mastery, why).
# This is authored curriculum data, entered through the same table and constraints
# as any tenant's skill graph; nothing downstream special-cases these competencies.
SKILL_GRAPH = [
    ("python.functions", "python.basics", 0.6, "Functions build on variables, control flow and basic types."),
    ("python.oop", "python.functions", 0.6, "Classes are built from functions, scope and state."),
    ("python.async", "python.functions", 0.6, "Coroutines are functions; scope and closures must be solid first."),
    ("sql.aggregation", "sql.joins", 0.6, "Meaningful aggregation usually runs over joined tables."),
    ("sql.window_functions", "sql.aggregation", 0.65, "Window functions generalise GROUP BY aggregation."),
    ("sql.indexing", "sql.joins", 0.6, "Index and plan tuning is driven by join and filter patterns."),
    ("de.etl_pipelines", "python.functions", 0.6, "Pipeline tasks are written as Python functions."),
    ("de.etl_pipelines", "sql.joins", 0.6, "Transformations depend on relational joins."),
    ("de.stream_processing", "de.etl_pipelines", 0.6, "Streaming extends batch pipeline concepts."),
    ("de.stream_processing", "python.async", 0.6, "Consumers rely on non-blocking I/O."),
    ("de.data_modeling", "sql.joins", 0.6, "Star schemas are queried with joins."),
    ("de.data_modeling", "sql.aggregation", 0.6, "Fact tables are consumed through aggregation."),
    ("ml.supervised", "python.functions", 0.6, "Model code is written in Python."),
    ("ml.evaluation_metrics", "ml.supervised", 0.6, "Metrics evaluate supervised models."),
    ("ml.feature_engineering", "ml.supervised", 0.55, "Feature choices are judged by model performance."),
    ("genai.embeddings", "python.functions", 0.6, "Embedding pipelines are written in Python."),
    ("genai.rag_architecture", "genai.embeddings", 0.65, "Retrieval is built on embeddings."),
    ("genai.rag_architecture", "genai.prompt_engineering", 0.6, "Grounded generation depends on prompt design."),
]


def seed_database():
    session = SessionLocal()
    try:
        print("Starting Adaptive LMS Stage 2 Database Seeding...")

        # ---------------------------------------------------------------------
        # 1. Organizations
        # ---------------------------------------------------------------------
        acme_org = session.query(Organization).filter_by(slug="acme-corp").first()
        if not acme_org:
            acme_org = Organization(
                id=uuid.uuid4(),
                name="Acme Corporation",
                slug="acme-corp",
                is_active=True,
                settings={"theme": "light", "allowed_domains": ["acme.com"], "max_users": 500},
            )
            session.add(acme_org)

        technova_org = session.query(Organization).filter_by(slug="technova").first()
        if not technova_org:
            technova_org = Organization(
                id=uuid.uuid4(),
                name="TechNova Systems",
                slug="technova",
                is_active=True,
                settings={"theme": "light", "allowed_domains": ["technova.com"], "max_users": 200},
            )
            session.add(technova_org)
        session.flush()
        print(f"  [OK] Verified Organizations: {acme_org.name}, {technova_org.name}")

        # ---------------------------------------------------------------------
        # 2. Users across all 5 roles
        # ---------------------------------------------------------------------
        user_specs = [
            ("sysadmin@adaptivelms.io", "Alexander SystemAdmin", "system_admin", acme_org.id),
            ("admin@acme.com", "Sarah Admin", "org_admin", acme_org.id),
            ("sarah.instructor@acme.com", "Sarah Instructor", "instructor", acme_org.id),
            ("marcus.manager@acme.com", "Marcus Miller", "manager", acme_org.id),
            ("alice.learner@acme.com", "Alice Adams", "learner", acme_org.id),
            ("bob.learner@acme.com", "Bob Bennett", "learner", acme_org.id),
            ("carol.learner@acme.com", "Carol Clark", "learner", acme_org.id),
            ("dan.learner@acme.com", "Dan Davis", "learner", acme_org.id),
            ("admin@technova.com", "Tara TechAdmin", "org_admin", technova_org.id),
            ("david.instructor@technova.com", "David Dean", "instructor", technova_org.id),
            ("rachel.manager@technova.com", "Rachel Ray", "manager", technova_org.id),
            ("elena.learner@technova.com", "Elena Evans", "learner", technova_org.id),
            ("frank.learner@technova.com", "Frank Foster", "learner", technova_org.id),
        ]

        role_catalogue = {r.code: r for r in session.query(RoleDefinition).all()}
        if not role_catalogue:
            raise RuntimeError("Role catalogue is empty. Run: alembic upgrade head")

        u_map = {}
        for email, full_name, role, org_id in user_specs:
            u = session.query(User).filter_by(email=email).first()
            if not u:
                u = User(
                    id=uuid.uuid4(),
                    org_id=org_id,
                    email=email,
                    password_hash=DEFAULT_PASSWORD_HASH,
                    full_name=full_name,
                    role=role,
                    is_active=True,
                )
                session.add(u)
                session.flush()
            u_map[email] = u

            # Role assignment lives in user_roles; users.role is the compatibility column.
            canonical = normalize_role(role)
            role_def = role_catalogue.get(canonical.value) if canonical else None
            if role_def is None:
                raise RuntimeError(f"Role '{role}' is not in the role catalogue. Run: alembic upgrade head")
            if not session.query(UserRole).filter_by(user_id=u.id, role_id=role_def.id).first():
                session.add(UserRole(user_id=u.id, role_id=role_def.id, org_id=u.org_id))
        session.flush()
        print(f"  [OK] Verified {len(u_map)} Users across 5 Roles")

        # ---------------------------------------------------------------------
        # 3. Teams & Memberships
        # ---------------------------------------------------------------------
        team_fe = session.query(Team).filter_by(name="Frontend Engineering Team", org_id=acme_org.id).first()
        if not team_fe:
            team_fe = Team(
                id=uuid.uuid4(),
                org_id=acme_org.id,
                name="Frontend Engineering Team",
                description="Client-side architecture and interactive application engineers",
                manager_id=u_map["marcus.manager@acme.com"].id,
            )
            session.add(team_fe)
            session.flush()

        team_data = session.query(Team).filter_by(name="Data Platform Team", org_id=acme_org.id).first()
        if not team_data:
            team_data = Team(
                id=uuid.uuid4(),
                org_id=acme_org.id,
                name="Data Platform Team",
                description="Data engineering, distributed analytics, and ML platform engineers",
                manager_id=u_map["marcus.manager@acme.com"].id,
            )
            session.add(team_data)
            session.flush()

        # Memberships
        for email, team_obj in [
            ("alice.learner@acme.com", team_fe),
            ("bob.learner@acme.com", team_fe),
            ("carol.learner@acme.com", team_data),
            ("dan.learner@acme.com", team_data),
        ]:
            mem = session.query(UserTeam).filter_by(user_id=u_map[email].id, team_id=team_obj.id).first()
            if not mem:
                session.add(UserTeam(user_id=u_map[email].id, team_id=team_obj.id, org_id=acme_org.id))
        session.flush()
        print("  [OK] Verified Teams and Cohort Memberships")

        # ---------------------------------------------------------------------
        # 4. Competency Framework (15 Domain Competencies)
        # ---------------------------------------------------------------------
        comp_specs = [
            # Python
            ("python.basics", "Python Core Syntax & Control Flow", "Variables, conditionals, loops, and basic data types in Python 3.11+", "understand"),
            ("python.functions", "Python Functions, Scope & Closures", "Function definitions, args/kwargs, first-class functions, and lexical closures", "apply"),
            ("python.oop", "Object-Oriented Programming & Inheritance", "Classes, polymorphism, inheritance, dunder methods, and design patterns", "analyze"),
            ("python.async", "Asynchronous Python & Concurrency", "Asyncio event loops, coroutines, tasks, and non-blocking I/O operations", "evaluate"),
            # SQL
            ("sql.joins", "Relational Joins & Set Operations", "Inner, left, right, outer joins, cross joins, and relational algebra", "apply"),
            ("sql.aggregation", "SQL Grouping & Aggregations", "GROUP BY, HAVING, complex multi-dimensional rollups, and conditional counts", "apply"),
            ("sql.window_functions", "Advanced SQL Window Functions", "PARTITION BY, ORDER BY, ROW_NUMBER, RANK, LEAD/LAG, and running totals", "analyze"),
            ("sql.indexing", "Database Query & Index Optimization", "B-Tree, GIN, BRIN indexes, EXPLAIN ANALYZE execution plans, and query tuning", "evaluate"),
            # Data Engineering
            ("de.etl_pipelines", "ETL/ELT Pipeline Orchestration", "Batch data processing, DAG task dependencies, data cleaning, and validation", "apply"),
            ("de.stream_processing", "Event Stream Processing", "Log-centric architectures, consumer groups, backpressure, and exactly-once delivery", "analyze"),
            ("de.data_modeling", "Dimensional Data Modeling", "Star schemas, snowflake schemas, slowly changing dimensions (SCD), and data marts", "create"),
            # Machine Learning
            ("ml.supervised", "Supervised Learning Algorithms", "Linear regression, logistic regression, decision trees, random forests, and gradient boosting", "apply"),
            ("ml.evaluation_metrics", "ML Model Evaluation & Diagnostics", "Precision, recall, F1 score, ROC-AUC, cross-validation, and bias-variance tradeoff", "evaluate"),
            ("ml.feature_engineering", "Feature Engineering & Preprocessing", "Encoding, scaling, handling missing values, feature selection, and dimensionality reduction", "analyze"),
            # AI & GenAI
            ("genai.prompt_engineering", "Prompt Engineering & Structured Outputs", "Few-shot prompting, chain-of-thought, system instruction design, and JSON schema constraints", "apply"),
            ("genai.rag_architecture", "Retrieval-Augmented Generation (RAG)", "Vector databases, chunking strategies, dense retrieval, and grounded citation verification", "create"),
            ("genai.embeddings", "Vector Embeddings & Semantic Search", "Cosine similarity, embedding models, pgvector indexing, and semantic reranking", "analyze"),
        ]

        comp_map = {}
        for code, name, desc, tax in comp_specs:
            c = session.query(Competency).filter_by(code=code, org_id=acme_org.id).first()
            if not c:
                c = Competency(
                    id=uuid.uuid4(),
                    org_id=acme_org.id,
                    code=code,
                    name=name,
                    description=desc,
                    taxonomy_level=tax,
                    domain=code.split(".")[0],
                    difficulty=BLOOM_DIFFICULTY[tax],
                )
                session.add(c)
                session.flush()
            comp_map[code] = c
        print(f"  [OK] Verified {len(comp_map)} Granular Competencies")

        # Skill graph (prerequisites). Idempotent; acyclicity is asserted before commit.
        for comp_code, prereq_code, min_mastery, rationale in SKILL_GRAPH:
            comp, prereq = comp_map[comp_code], comp_map[prereq_code]
            if not session.query(CompetencyPrerequisite).filter_by(
                competency_id=comp.id, prerequisite_id=prereq.id
            ).first():
                session.add(CompetencyPrerequisite(
                    competency_id=comp.id, prerequisite_id=prereq.id, org_id=acme_org.id,
                    min_mastery=min_mastery, rationale=rationale,
                ))
        session.flush()
        graph_edges = [(e.competency_id, e.prerequisite_id) for e in
                       session.query(CompetencyPrerequisite).filter_by(org_id=acme_org.id)]
        levels = topological_levels([c.id for c in comp_map.values()], graph_edges)  # raises on a cycle
        print(f"  [OK] Verified skill graph: {len(graph_edges)} prerequisite edges, depth {max(levels.values())}")

        # ---------------------------------------------------------------------
        # 5. The 5 Real Courses with Modules, Video, Article, Quiz, Assignment
        # ---------------------------------------------------------------------
        courses_data = [
            # Course 1: Python Fundamentals
            {
                "title": "Python Fundamentals & Software Engineering",
                "code": "PY-FUND-101",
                "description": "Master clean, idiomatic Python programming from control flow and data structures to object-oriented architecture and asynchronous concurrency.",
                "category": "Computer Science",
                "difficulty": "beginner",
                "thumbnail_url": "https://images.unsplash.com/photo-1526379095098-d400fd0bf935?w=800&auto=format&fit=crop&q=80",
                "primary_competencies": ["python.basics", "python.functions", "python.oop", "python.async"],
                "modules": [
                    {
                        "title": "Module 1: Functions, Closures & Functional Paradigms",
                        "description": "Understanding function arguments, lexical scoping, lambda functions, and closures in modern Python.",
                        "sequence": 1,
                        "competency": "python.functions",
                        "video_title": "How-To: Python Decorators, Closure, Nesting & First Class Functions",
                        "video_url": "https://www.youtube.com/watch?v=aJc5MuJbOr0",
                        "video_author": "Mnemonic Academy",
                        "article_title": "Mastering Python Functions: Scope, LEGB Rule, and Closures",
                        "article_text": """# Mastering Python Functions: Scope, LEGB Rule, and Closures

Functions in Python are first-class citizens: they can be passed as arguments, returned from other functions, and bound to variables.

## Variable Scoping and the LEGB Rule
Python resolves variable names using the **LEGB** rule:
1. **L**ocal: Defined inside the current function.
2. **E**nclosing: Defined in outer/enclosing functions (for nested functions).
3. **G**lobal: Defined at the top level of the module or declared with `global`.
4. **B**uilt-in: Reserved keywords and built-in functions like `len` or `range`.

```python
def make_multiplier(factor: int):
    # 'factor' is in the enclosing scope
    def multiplier(number: int) -> int:
        return number * factor  # Free variable capture (Closure)
    return multiplier

double = make_multiplier(2)
print(double(5)) # Output: 10
```

## Mutable Default Arguments Pitfall
A classic misconception in Python is defining functions with mutable default arguments:
```python
# SUBOPTIMAL (Causes shared mutable state across invocations)
def append_to_list(item, target_list=[]):
    target_list.append(item)
    return target_list

# RECOMMENDED IDIOM
def append_to_list_safe(item, target_list=None):
    if target_list is None:
        target_list = []
    target_list.append(item)
    return target_list
```
Always use immutable sentinel values (`None`) as default arguments for collections.
""",
                        "quiz_questions": [
                            {
                                "text": "What happens when you use a mutable object (like a list or dict) as a default parameter value in a Python function definition?",
                                "options": [
                                    {"id": "a", "text": "A new copy of the object is created every time the function is called."},
                                    {"id": "b", "text": "The default object is evaluated once at definition time and shared across all subsequent calls that omit the argument."},
                                    {"id": "c", "text": "Python raises a TypeError at runtime."},
                                    {"id": "d", "text": "The object is automatically frozen as an immutable tuple."},
                                ],
                                "correct": {"answer": "b"},
                                "explanation": "Default argument values in Python are evaluated once when the function definition is executed, creating a single persistent object in memory that is shared across calls.",
                                "error_type": "CONCEPTUAL",
                                "difficulty": 0.45,
                                "discrimination": 1.2,
                            },
                            {
                                "text": "Which keyword is required inside a nested function if you wish to reassign a variable belonging to the immediate outer enclosing function without declaring it global?",
                                "options": [
                                    {"id": "a", "text": "global"},
                                    {"id": "b", "text": "outer"},
                                    {"id": "c", "text": "nonlocal"},
                                    {"id": "d", "text": "enclosing"},
                                ],
                                "correct": {"answer": "c"},
                                "explanation": "The 'nonlocal' statement causes listed identifiers to refer to previously bound variables in the nearest enclosing scope excluding globals.",
                                "error_type": "PROCEDURAL",
                                "difficulty": 0.40,
                                "discrimination": 1.1,
                            },
                        ],
                        "assignment": {
                            "title": "Build a Configurable Rate-Limiter Decorator",
                            "instructions": "Write a Python decorator `@rate_limit(max_calls: int, period_seconds: float)` using closures and `time.monotonic()` that raises a custom `RateLimitExceeded` exception when a function is invoked too rapidly.",
                            "difficulty": "intermediate",
                            "rubric": {
                                "closure_state_isolation": {"weight": 0.4, "max": 40},
                                "time_window_accuracy": {"weight": 0.4, "max": 40},
                                "docstring_preservation_functools_wraps": {"weight": 0.2, "max": 20},
                            },
                        },
                    },
                    {
                        "title": "Module 2: Object-Oriented Architecture & Polymorphism",
                        "description": "Classes, encapsulation, inheritance hierarchy, abstract base classes, and polymorphism.",
                        "sequence": 2,
                        "competency": "python.oop",
                        "video_title": "Python OOP Tutorial 4: Inheritance - Creating Subclasses",
                        "video_url": "https://www.youtube.com/watch?v=RSl87lqOXDE",
                        "video_author": "Corey Schafer",
                        "article_title": "Modern Python OOP: Abstract Base Classes, Dunder Methods, and Composition",
                        "article_text": """# Modern Python OOP: Abstract Base Classes, Dunder Methods, and Composition

Object-oriented programming in Python is dynamic and expressive. Python relies on protocols and duck typing ("if it walks like a duck and quacks like a duck, it is a duck").

## Abstract Base Classes (ABCs)
Use the `abc` module to define formal interfaces:
```python
from abc import ABC, abstractmethod

class DataStore(ABC):
    @abstractmethod
    def read(self, key: str) -> bytes:
        pass

    @abstractmethod
    def write(self, key: str, value: bytes) -> None:
        pass
```

## Method Resolution Order (MRO)
Python uses the C3 Superconcurrency Linearization algorithm to resolve method inheritance in multiple inheritance trees (`ClassName.__mro__`).
""",
                        "quiz_questions": [
                            {
                                "text": "In Python multiple inheritance, which algorithm determines the exact order in which classes are searched when resolving a method or attribute?",
                                "options": [
                                    {"id": "a", "text": "Depth-First Search with Left-to-Right Priority"},
                                    {"id": "b", "text": "Breadth-First Search with Right-to-Left Priority"},
                                    {"id": "c", "text": "C3 Linearization (MRO)"},
                                    {"id": "d", "text": "Dijkstra's Shortest Path Algorithm"},
                                ],
                                "correct": {"answer": "c"},
                                "explanation": "Python utilizes C3 Linearization to guarantee that subclasses precede their parents and multiple parent orders are preserved consistently.",
                                "error_type": "CONCEPTUAL",
                                "difficulty": 0.65,
                                "discrimination": 1.35,
                            },
                        ],
                        "assignment": {
                            "title": "Implement an Extensible Plugin Architecture",
                            "instructions": "Create an abstract `PluginBase` class using `abc.ABC` and build two concrete plugins (JSONSerializer and CSVSerializer) that dynamically register themselves with a central `PluginRegistry`.",
                            "difficulty": "intermediate",
                            "rubric": {
                                "abc_enforcement": {"weight": 0.35, "max": 35},
                                "registry_pattern": {"weight": 0.45, "max": 45},
                                "type_hinting": {"weight": 0.20, "max": 20},
                            },
                        },
                    },
                ],
            },

            # Course 2: SQL for Data Analytics
            {
                "title": "SQL for Data Analytics & Performance Optimization",
                "code": "SQL-ANALYTICS-201",
                "description": "Master advanced relational SQL from complex multi-table joins and analytical window functions to execution plan inspection and index tuning.",
                "category": "Data Science",
                "difficulty": "intermediate",
                "thumbnail_url": "https://images.unsplash.com/photo-1544383835-bda2bc66a55d?w=800&auto=format&fit=crop&q=80",
                "primary_competencies": ["sql.joins", "sql.aggregation", "sql.window_functions", "sql.indexing"],
                "modules": [
                    {
                        "title": "Module 1: Analytical Window Functions & Partitions",
                        "description": "Compute running totals, rankings, moving averages, and lead/lag trends across partitioned datasets.",
                        "sequence": 1,
                        "competency": "sql.window_functions",
                        "video_title": "SQL Window Functions | Clearly Explained | PARTITION BY, ORDER BY, ROW_NUMBER, RANK, DENSE_RANK",
                        "video_url": "https://www.youtube.com/watch?v=rIcB4zMYMas",
                        "video_author": "Maven Analytics",
                        "article_title": "Mastering SQL Window Functions: Real-World Business Analytics",
                        "article_text": """# Mastering SQL Window Functions: Real-World Business Analytics

Unlike aggregate functions with `GROUP BY` that collapse rows, window functions calculate values across a set of table rows while preserving individual row identity.

```sql
SELECT
    learner_id,
    course_id,
    score,
    AVG(score) OVER(PARTITION BY course_id) AS course_avg_score,
    RANK() OVER(PARTITION BY course_id ORDER BY score DESC) as rank_in_course,
    LAG(score, 1) OVER(PARTITION BY learner_id ORDER BY submitted_at ASC) as prev_attempt_score
FROM quiz_submissions;
```
""",
                        "quiz_questions": [
                            {
                                "text": "What is the primary difference between `RANK()` and `DENSE_RANK()` when evaluating tied values in an ordered window partition?",
                                "options": [
                                    {"id": "a", "text": "RANK() assigns identical ranks and skips subsequent rank numbers; DENSE_RANK() leaves no gaps in ranking sequence."},
                                    {"id": "b", "text": "DENSE_RANK() sorts descending while RANK() sorts ascending."},
                                    {"id": "c", "text": "RANK() requires an aggregate function inside its parenthesis."},
                                    {"id": "d", "text": "There is no difference; they are aliases."},
                                ],
                                "correct": {"answer": "a"},
                                "explanation": "RANK() produces gaps in the sequence following ties (e.g. 1, 2, 2, 4), whereas DENSE_RANK() assigns consecutive integers without gaps (e.g. 1, 2, 2, 3).",
                                "error_type": "CONCEPTUAL",
                                "difficulty": 0.50,
                                "discrimination": 1.15,
                            },
                        ],
                        "assignment": {
                            "title": "Cohort Retention & MoM Revenue Analytics Query",
                            "instructions": "Write an optimized SQL query using window functions (`SUM() OVER`, `LAG()`, `PARTITION BY`) to compute month-over-month learner retention and running cumulative platform active users.",
                            "difficulty": "advanced",
                            "rubric": {
                                "correct_partitioning": {"weight": 0.4, "max": 40},
                                "running_total_framing": {"weight": 0.4, "max": 40},
                                "query_efficiency": {"weight": 0.2, "max": 20},
                            },
                        },
                    },
                ],
            },

            # Course 3: Data Engineering Fundamentals
            {
                "title": "Data Engineering Fundamentals & Distributed Streaming",
                "code": "DE-PIPELINES-301",
                "description": "Build production-grade data pipelines, stream processing systems with Redis Streams/Kafka, and dimensional data models.",
                "category": "Engineering",
                "difficulty": "intermediate",
                "thumbnail_url": "https://images.unsplash.com/photo-1558494949-ef010cbdcc31?w=800&auto=format&fit=crop&q=80",
                "primary_competencies": ["de.etl_pipelines", "de.stream_processing", "de.data_modeling"],
                "modules": [
                    {
                        "title": "Module 1: Resilient Stream Processing & Message Logs",
                        "description": "Partitioning, consumer groups, offsets, and backpressure management in real-time streaming architectures.",
                        "sequence": 1,
                        "competency": "de.stream_processing",
                        "video_title": "How do Kafka Consumer Groups and Consumer Offsets work in Apache Kafka?",
                        "video_url": "https://www.youtube.com/watch?v=9o5LAbPNc28",
                        "video_author": "Conduktor",
                        "article_title": "Building Resilient Event-Driven Pipelines with Redis Streams",
                        "article_text": """# Building Resilient Event-Driven Pipelines with Redis Streams

Redis Streams provides an append-only, ordered message log with support for Consumer Groups, allowing distributed workers to consume distinct partitions of high-throughput telemetry without collision.

## Core Commands & Semantics
- `XADD`: Ingests an immutable learning event into the stream with monotonic ID.
- `XREADGROUP`: Reads unassigned messages for a specific consumer within a consumer group.
- `XACK`: Acknowledges successful message processing, removing it from the Pending Entries List (PEL).
""",
                        "quiz_questions": [
                            {
                                "text": "In a distributed streaming architecture using consumer groups, what happens to a message if a consumer worker crashes before sending an acknowledgement (XACK)?",
                                "options": [
                                    {"id": "a", "text": "The message is immediately deleted to prevent queue blockage."},
                                    {"id": "b", "text": "The message remains in the Pending Entries List (PEL) and can be reclaimed by another active worker."},
                                    {"id": "c", "text": "The stream halts all ingestion until the dead worker restarts."},
                                    {"id": "d", "text": "The message is moved directly to the system root partition."},
                                ],
                                "correct": {"answer": "b"},
                                "explanation": "Unacknowledged messages stay in the PEL with their idle time increasing, allowing failover workers to claim them using commands like XAUTOCLAIM.",
                                "error_type": "CONCEPTUAL",
                                "difficulty": 0.55,
                                "discrimination": 1.30,
                            },
                        ],
                        "assignment": {
                            "title": "Implement an Idempotent Stream Consumer Worker",
                            "instructions": "Build an asynchronous Python worker that reads telemetry from a stream, processes JSON events with error classification, and guarantees idempotency using PostgreSQL transaction locks.",
                            "difficulty": "advanced",
                            "rubric": {
                                "consumer_group_lifecycle": {"weight": 0.4, "max": 40},
                                "idempotency_deduplication": {"weight": 0.4, "max": 40},
                                "graceful_shutdown": {"weight": 0.2, "max": 20},
                            },
                        },
                    },
                ],
            },

            # Course 4: Machine Learning Fundamentals
            {
                "title": "Machine Learning Fundamentals & Statistical Evaluation",
                "code": "ML-CORE-401",
                "description": "Understand core supervised algorithms, mathematical loss functions, feature engineering, and rigorous model evaluation.",
                "category": "Artificial Intelligence",
                "difficulty": "advanced",
                "thumbnail_url": "https://images.unsplash.com/photo-1555939594-58d7cb561ad1?w=800&auto=format&fit=crop&q=80",
                "primary_competencies": ["ml.supervised", "ml.evaluation_metrics", "ml.feature_engineering"],
                "modules": [
                    {
                        "title": "Module 1: Classification Diagnostics, Precision-Recall & ROC-AUC",
                        "description": "Evaluating classification models under class imbalance, understanding false positives vs false negatives.",
                        "sequence": 1,
                        "competency": "ml.evaluation_metrics",
                        "video_title": "ROC and AUC, Clearly Explained!",
                        "video_url": "https://www.youtube.com/watch?v=4jRBRDbJemM",
                        "video_author": "StatQuest with Josh Starmer",
                        "article_title": "Evaluating Machine Learning Models Under Severe Class Imbalance",
                        "article_text": """# Evaluating Machine Learning Models Under Severe Class Imbalance

When predicting rare events (such as learner dropout or fraud where positive cases are < 5%), raw Accuracy is deceptive. A dummy classifier predicting 100% negative achieves 95% accuracy while possessing zero diagnostic utility.

## Key Diagnostic Metrics
- **Precision**: TP / (TP + FP) — What proportion of predicted positive cases were actual positives?
- **Recall (Sensitivity)**: TP / (TP + FN) — What proportion of actual positive cases were successfully identified?
- **F1 Score**: Harmonic mean of Precision and Recall.
- **PR-AUC**: Area under the Precision-Recall Curve, preferred over ROC-AUC for heavy class skew.
""",
                        "quiz_questions": [
                            {
                                "text": "Why is the Precision-Recall AUC curve generally preferred over the standard ROC-AUC curve when evaluating models on highly imbalanced datasets?",
                                "options": [
                                    {"id": "a", "text": "PR-AUC does not include True Negatives in its calculation, preventing large negative majorities from inflating perceived performance."},
                                    {"id": "b", "text": "ROC-AUC is mathematically undefined when negative cases exceed positive cases."},
                                    {"id": "c", "text": "PR-AUC executes faster computationally."},
                                    {"id": "d", "text": "Precision cannot be computed on balanced datasets."},
                                ],
                                "correct": {"answer": "a"},
                                "explanation": "The True Negative count in ROC-AUC causes the False Positive Rate (FP / (FP + TN)) to remain deceptively small when TN is vast, whereas Precision focuses directly on the minority positive class.",
                                "error_type": "CONCEPTUAL",
                                "difficulty": 0.60,
                                "discrimination": 1.25,
                            },
                        ],
                        "assignment": {
                            "title": "Build a Dropout Risk Prediction Pipeline with Scikit-Learn",
                            "instructions": "Train a Gradient Boosting Classifier on synthetic student interaction data, tune classification thresholds to maximize Recall for at-risk learners, and plot the Precision-Recall curve.",
                            "difficulty": "advanced",
                            "rubric": {
                                "preprocessing_and_pipeline": {"weight": 0.35, "max": 35},
                                "threshold_tuning": {"weight": 0.45, "max": 45},
                                "metric_interpretation": {"weight": 0.20, "max": 20},
                            },
                        },
                    },
                ],
            },

            # Course 5: AI & Generative AI Fundamentals
            {
                "title": "AI & Generative AI: Architecture, RAG & LLM Systems",
                "code": "GENAI-LLM-501",
                "description": "Understand transformer foundations, prompt engineering with structured constraints, vector search with pgvector, and grounded RAG systems.",
                "category": "Artificial Intelligence",
                "difficulty": "advanced",
                "thumbnail_url": "https://images.unsplash.com/photo-1677442136019-21780efad99a?w=800&auto=format&fit=crop&q=80",
                "primary_competencies": ["genai.prompt_engineering", "genai.rag_architecture", "genai.embeddings"],
                "modules": [
                    {
                        "title": "Module 1: Grounded Retrieval-Augmented Generation & Citation Verification",
                        "description": "Designing deterministic RAG pipelines, chunking policies, vector indexing, and zero-hallucination citation validation.",
                        "sequence": 1,
                        "competency": "genai.rag_architecture",
                        "video_title": "Retrieval Augmented Generation (RAG) Explained: Embedding, Sentence BERT, Vector Database (HNSW)",
                        "video_url": "https://www.youtube.com/watch?v=rhZgXNdhWDY",
                        "video_author": "Umar Jamil",
                        "article_title": "Production RAG Architecture: Grounding, Vector Search, and Hallucination Verification",
                        "article_text": """# Production RAG Architecture: Grounding, Vector Search, and Hallucination Verification

Generative AI systems deployed in enterprise environments cannot rely on raw unconstrained LLM responses. They must be grounded in verified contextual evidence with strict auditability.

## The Evidence-Grounded Lifecycle
1. **Deterministic Analytics**: Execute SQL queries to aggregate counts, trends, and risk signals before LLM invocation.
2. **Evidence Packaging**: Format factual metrics into numbered evidence items (`[E-1]`, `[E-2]`).
3. **Structured Prompting**: Instruct the model to cite evidence keys and output valid JSON conforming to a Pydantic schema.
4. **Citation Validation**: Programmatically verify that every cited claim references a real evidence ID from the input package.
""",
                        "quiz_questions": [
                            {
                                "text": "In a mission-critical Enterprise AI reporting system, why must deterministic evidence extraction precede the LLM call rather than asking the LLM to compute statistics directly from raw text?",
                                "options": [
                                    {"id": "a", "text": "LLMs are probabilistic token predictors prone to arithmetic and aggregation hallucinations on numeric data."},
                                    {"id": "b", "text": "Databases cannot execute SQL queries if an LLM is connected."},
                                    {"id": "c", "text": "JSON output schemas are unsupported by modern neural networks."},
                                    {"id": "d", "text": "Evidence packaging increases token latency by over 90%."},
                                ],
                                "correct": {"answer": "a"},
                                "explanation": "Deterministic SQL engines guarantee mathematical accuracy for metrics, averages, and distributions, allowing the LLM to focus on qualitative synthesis and explainability.",
                                "error_type": "CONCEPTUAL",
                                "difficulty": 0.50,
                                "discrimination": 1.30,
                            },
                        ],
                        "assignment": {
                            "title": "Implement a Citation-Verifying RAG Guardrail",
                            "instructions": "Write a Python validation function that parses LLM narrative responses, extracts `[E-#]` regex citations, cross-references an evidence dictionary, and calculates an audit grounding score.",
                            "difficulty": "advanced",
                            "rubric": {
                                "regex_extraction": {"weight": 0.3, "max": 30},
                                "citation_cross_verification": {"weight": 0.4, "max": 40},
                                "penalty_scoring_logic": {"weight": 0.3, "max": 30},
                            },
                        },
                    },
                ],
            },
        ]

        # Process each course
        instructor_user = u_map.get("sarah.instructor@acme.com")
        instructor_id = instructor_user.id if instructor_user else None

        for c_data in courses_data:
            course = session.query(Course).filter_by(code=c_data["code"], org_id=acme_org.id).first()
            if not course:
                course = Course(
                    id=uuid.uuid4(),
                    org_id=acme_org.id,
                    title=c_data["title"],
                    code=c_data["code"],
                    description=c_data["description"],
                    status="published",
                    category=c_data.get("category", "Computer Science"),
                    difficulty=c_data.get("difficulty", "intermediate"),
                    thumbnail_url=c_data.get("thumbnail_url"),
                    created_by_id=instructor_id,
                    instructor_id=instructor_id,
                    course_metadata={"target_audience": "Engineers & Data Practitioners", "level": "Comprehensive"},
                )
                session.add(course)
                session.flush()
            else:
                course.category = c_data.get("category", course.category or "Computer Science")
                course.difficulty = c_data.get("difficulty", course.difficulty or "intermediate")
                course.thumbnail_url = c_data.get("thumbnail_url", course.thumbnail_url)
                course.instructor_id = instructor_id
                session.flush()

            # Course Competencies
            for comp_code in c_data["primary_competencies"]:
                if comp_code in comp_map:
                    cc = session.query(CourseCompetency).filter_by(course_id=course.id, competency_id=comp_map[comp_code].id).first()
                    if not cc:
                        session.add(CourseCompetency(course_id=course.id, competency_id=comp_map[comp_code].id, target_mastery=0.85, is_primary=True))
            session.flush()

            # Modules
            for m_data in c_data["modules"]:
                module = session.query(Module).filter_by(course_id=course.id, sequence_order=m_data["sequence"]).first()
                if not module:
                    module = Module(
                        id=uuid.uuid4(),
                        org_id=acme_org.id,
                        course_id=course.id,
                        title=m_data["title"],
                        description=m_data["description"],
                        sequence_order=m_data["sequence"],
                        estimated_duration_mins=45,
                    )
                    session.add(module)
                    session.flush()

                # Module Competency Mapping
                target_comp = comp_map.get(m_data["competency"])
                if target_comp:
                    mc = session.query(ModuleCompetency).filter_by(module_id=module.id, competency_id=target_comp.id).first()
                    if not mc:
                        session.add(ModuleCompetency(module_id=module.id, competency_id=target_comp.id, weight=1.0))
                session.flush()

                # Content Item 1: VIDEO
                v_item = session.query(ContentItem).filter_by(module_id=module.id, content_type="VIDEO").first()
                if not v_item:
                    v_item = ContentItem(
                        id=uuid.uuid4(),
                        org_id=acme_org.id,
                        course_id=course.id,
                        module_id=module.id,
                        title=m_data["video_title"],
                        description=f"Instructional video lecture for {m_data['title']}",
                        content_type="VIDEO",
                        content_url=m_data["video_url"],
                        source_type="youtube",
                        source_url=m_data["video_url"],
                        duration_seconds=0,  # unknown: YouTube reports the real length to the player at playback
                        order_index=1,
                        status="published",
                        item_metadata={"provider": "youtube", "author": m_data["video_author"]},
                    )
                    session.add(v_item)
                    session.flush()
                else:
                    # Refresh rows created by earlier seeds, which pointed at a domain that serves nothing.
                    v_item.title = m_data["video_title"]
                    v_item.content_url = m_data["video_url"]
                    v_item.source_type = "youtube"
                    v_item.source_url = m_data["video_url"]
                    v_item.duration_seconds = 0
                    v_item.item_metadata = {"provider": "youtube", "author": m_data["video_author"]}

                # Content Item 2: ARTICLE
                a_item = session.query(ContentItem).filter_by(module_id=module.id, content_type="ARTICLE").first()
                if not a_item:
                    a_item = ContentItem(
                        id=uuid.uuid4(),
                        org_id=acme_org.id,
                        course_id=course.id,
                        module_id=module.id,
                        title=m_data["article_title"],
                        description=f"In-depth reading article and code guide for {m_data['title']}",
                        content_type="ARTICLE",
                        text_content=m_data["article_text"],
                        raw_text=m_data["article_text"],
                        duration_seconds=reading_seconds(m_data["article_text"]),
                        item_metadata={"duration_basis": "reading_time_estimate"},
                        order_index=2,
                        chunk_count=1,
                        status="published",
                    )
                    session.add(a_item)
                    session.flush()

                    # Create Content Chunk for RAG / Vector search
                    chunk = ContentChunk(
                        id=uuid.uuid4(),
                        org_id=acme_org.id,
                        content_item_id=a_item.id,
                        chunk_index=0,
                        text_content=m_data["article_text"][:800],
                        token_count=150,
                    )
                    session.add(chunk)
                elif not a_item.duration_seconds:
                    a_item.duration_seconds = reading_seconds(a_item.text_content or "")
                    a_item.item_metadata = {"duration_basis": "reading_time_estimate"}

                # Content Item 3: Assessment Items (Psychometric question bank)
                for q_spec in m_data["quiz_questions"]:
                    existing_q = session.query(AssessmentItem).filter_by(module_id=module.id, question_text=q_spec["text"]).first()
                    if not existing_q and target_comp:
                        q_item = AssessmentItem(
                            id=uuid.uuid4(),
                            org_id=acme_org.id,
                            module_id=module.id,
                            competency_id=target_comp.id,
                            question_text=q_spec["text"],
                            question_type="multiple_choice",
                            options=q_spec["options"],
                            correct_answer=q_spec["correct"],
                            explanation=q_spec["explanation"],
                            error_type=q_spec.get("error_type", "CONCEPTUAL"),
                            difficulty_score=q_spec.get("difficulty", 0.5),
                            discrimination_index=q_spec.get("discrimination", 1.0),
                            is_ai_generated=False,
                            quality_flag="approved",
                        )
                        session.add(q_item)

                # Quiz & Quiz Questions Model
                quiz = session.query(Quiz).filter_by(module_id=module.id).first()
                if not quiz and m_data.get("quiz_questions"):
                    quiz = Quiz(
                        id=uuid.uuid4(),
                        org_id=acme_org.id,
                        course_id=course.id,
                        module_id=module.id,
                        title=f"Quiz: {m_data['title']}",
                        description=f"Knowledge verification and mastery assessment for {m_data['title']}",
                        time_limit_mins=20,
                        passing_score=70.0,
                        max_attempts=3,
                        is_adaptive=False,
                    )
                    session.add(quiz)
                    session.flush()

                    for q_idx, q_spec in enumerate(m_data["quiz_questions"]):
                        qq = QuizQuestion(
                            id=uuid.uuid4(),
                            quiz_id=quiz.id,
                            competency_id=target_comp.id if target_comp else None,
                            question_text=q_spec["text"],
                            question_type="multiple_choice",
                            points=10,
                            order_index=q_idx,
                            explanation=q_spec.get("explanation"),
                        )
                        session.add(qq)
                        session.flush()

                        for o_idx, opt in enumerate(q_spec["options"]):
                            is_corr = (opt["id"] == q_spec["correct"].get("answer"))
                            qo = QuizOption(
                                id=uuid.uuid4(),
                                question_id=qq.id,
                                option_text=opt["text"],
                                is_correct=is_corr,
                                order_index=o_idx,
                                explanation=q_spec.get("explanation") if is_corr else None,
                            )
                            session.add(qo)

                # Content Item for QUIZ (so it appears in module curriculum syllabus)
                quiz_item = session.query(ContentItem).filter_by(module_id=module.id, content_type="QUIZ").first()
                if not quiz_item and quiz:
                    quiz_item = ContentItem(
                        id=uuid.uuid4(),
                        org_id=acme_org.id,
                        course_id=course.id,
                        module_id=module.id,
                        title=f"Assessment: {m_data['title']}",
                        description=f"Curriculum assessment quiz for {m_data['title']}",
                        content_type="QUIZ",
                        duration_seconds=quiz.time_limit_mins * 60,  # the configured time limit
                        order_index=3,
                        status="published",
                        item_metadata={"quiz_id": str(quiz.id)},
                    )
                    session.add(quiz_item)
                    session.flush()
                if quiz and quiz_item:
                    if quiz.content_item_id is None:
                        quiz.content_item_id = quiz_item.id  # explicit link (unique)
                    quiz_item.duration_seconds = quiz.time_limit_mins * 60
                    session.flush()

                # Content Item 4: ASSIGNMENT
                asg_spec = m_data.get("assignment")
                if asg_spec:
                    existing_asg = session.query(Assignment).filter_by(module_id=module.id, title=asg_spec["title"]).first()
                    if not existing_asg and target_comp:
                        assignment = Assignment(
                            id=uuid.uuid4(),
                            org_id=acme_org.id,
                            course_id=course.id,
                            module_id=module.id,
                            competency_id=target_comp.id,
                            title=asg_spec["title"],
                            instructions=asg_spec["instructions"],
                            difficulty=asg_spec["difficulty"],
                            max_score=100.0,
                            rubric=asg_spec["rubric"],
                            status="published",
                        )
                        session.add(assignment)

                # The assignment is presented in the outline as its own lesson item.
                if asg_spec:
                    assignment_row = session.query(Assignment).filter_by(module_id=module.id, title=asg_spec["title"]).first()
                    if assignment_row and assignment_row.content_item_id is None:
                        asg_item = ContentItem(
                            id=uuid.uuid4(), org_id=acme_org.id, course_id=course.id, module_id=module.id,
                            title=f"Lab: {asg_spec['title']}",
                            description=f"Hands-on assignment for {m_data['title']}",
                            content_type="ASSIGNMENT", duration_seconds=0, order_index=4, status="published",
                            item_metadata={"assignment_id": str(assignment_row.id)},
                        )
                        session.add(asg_item)
                        session.flush()
                        assignment_row.content_item_id = asg_item.id
                        session.flush()

                # Content Competencies mappings
                if target_comp:
                    for ci in [v_item, a_item, quiz_item]:
                        if ci:
                            existing_cc = session.query(ContentCompetency).filter_by(content_item_id=ci.id, competency_id=target_comp.id).first()
                            if not existing_cc:
                                session.add(ContentCompetency(content_item_id=ci.id, competency_id=target_comp.id, weight=1.0))

        session.commit()
        print("  [OK] Seeded 5 Full Production Courses with 4 Modalities (Video, Article, Quiz, Lab)!")

        # ---------------------------------------------------------------------
        # 6. Enroll Learners into all 5 Courses & Seed Realistic Progress
        # ---------------------------------------------------------------------
        all_courses = session.query(Course).filter_by(org_id=acme_org.id).all()
        acme_learners = [
            u_map["alice.learner@acme.com"],
            u_map["bob.learner@acme.com"],
            u_map["carol.learner@acme.com"],
            u_map["dan.learner@acme.com"],
        ]

        for course in all_courses:
            for learner in acme_learners:
                existing_enr = session.query(Enrollment).filter_by(user_id=learner.id, course_id=course.id).first()
                if not existing_enr:
                    enr = Enrollment(
                        id=uuid.uuid4(),
                        org_id=acme_org.id,
                        user_id=learner.id,
                        course_id=course.id,
                        status="active",
                        progress_pct=0.0,
                        enrolled_at=datetime.utcnow() - timedelta(days=14),
                        last_activity_at=datetime.utcnow(),
                    )
                    session.add(enr)
        session.flush()

        # Seed rich progress for Alice in Python course (PY-FUND-101)
        alice = u_map["alice.learner@acme.com"]
        py_course = session.query(Course).filter_by(code="PY-FUND-101", org_id=acme_org.id).first()
        if py_course:
            alice_py_enr = session.query(Enrollment).filter_by(user_id=alice.id, course_id=py_course.id).first()
            if alice_py_enr:
                alice_py_enr.progress_pct = 35.0
                alice_py_enr.last_activity_at = datetime.utcnow()

            # Find module 1 items and complete them
            py_m1 = session.query(Module).filter_by(course_id=py_course.id, sequence_order=1).first()
            if py_m1:
                # Assignments complete only through a submission, so demo history skips them.
                m1_items = [i for i in session.query(ContentItem).filter_by(module_id=py_m1.id).all()
                            if i.content_type != "ASSIGNMENT"]
                for item in m1_items:
                    cp = session.query(ContentProgress).filter_by(user_id=alice.id, content_item_id=item.id).first()
                    if not cp:
                        cp = ContentProgress(
                            id=uuid.uuid4(),
                            org_id=alice.org_id,
                            user_id=alice.id,
                            content_item_id=item.id,
                            status="completed",
                            progress_percent=100.0,
                            time_spent_seconds=item.duration_seconds or 420,
                            last_accessed_at=datetime.utcnow() - timedelta(hours=2),
                            completed_at=datetime.utcnow() - timedelta(hours=2),
                        )
                        session.add(cp)

                # Record successful quiz attempt for module 1 quiz
                py_quiz = session.query(Quiz).filter_by(module_id=py_m1.id).first()
                if py_quiz:
                    q_att = session.query(QuizAttempt).filter_by(quiz_id=py_quiz.id, user_id=alice.id).first()
                    if not q_att:
                        q_att = QuizAttempt(
                            id=uuid.uuid4(),
                            quiz_id=py_quiz.id,
                            user_id=alice.id,
                            score=100.0,
                            passed=True,
                            attempt_number=1,
                            started_at=datetime.utcnow() - timedelta(hours=3),
                            completed_at=datetime.utcnow() - timedelta(hours=2, minutes=45),
                        )
                        session.add(q_att)
                        session.flush()

                        for qq in py_quiz.questions:
                            corr_opt = next((o for o in qq.options if o.is_correct), None)
                            if corr_opt:
                                resp = QuestionResponse(
                                    id=uuid.uuid4(),
                                    attempt_id=q_att.id,
                                    question_id=qq.id,
                                    selected_option_id=corr_opt.id,
                                    is_correct=True,
                                    points_awarded=float(qq.points),
                                )
                                session.add(resp)

            # Module 2 video in progress
            py_m2 = session.query(Module).filter_by(course_id=py_course.id, sequence_order=2).first()
            if py_m2:
                m2_video = session.query(ContentItem).filter_by(module_id=py_m2.id, content_type="VIDEO").first()
                if m2_video:
                    cp2 = session.query(ContentProgress).filter_by(user_id=alice.id, content_item_id=m2_video.id).first()
                    if not cp2:
                        cp2 = ContentProgress(
                            id=uuid.uuid4(),
                            org_id=alice.org_id,
                            user_id=alice.id,
                            content_item_id=m2_video.id,
                            status="in_progress",
                            progress_percent=45.0,
                            time_spent_seconds=240,
                            last_accessed_at=datetime.utcnow() - timedelta(minutes=30),
                        )
                        session.add(cp2)

        session.commit()
        print(f"  [OK] Enrolled {len(acme_learners)} Learners and seeded realistic progress & quiz attempts.")
        print("\nStage 2 Database Seeding Completed Successfully! 100% Dynamic.")

    except Exception as e:
        session.rollback()
        print(f"  [FAIL] Seeding failed with error: {e}")
        raise
    finally:
        session.close()


if __name__ == "__main__":
    seed_database()
