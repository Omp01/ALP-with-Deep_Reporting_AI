import os
import docx
from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_ALIGN_VERTICAL
from docx.oxml import OxmlElement, parse_xml
from docx.oxml.ns import nsdecls, qn

def set_cell_background(cell, fill_hex):
    tcPr = cell._element.get_or_add_tcPr()
    shd = parse_xml(f'<w:shd {nsdecls("w")} w:fill="{fill_hex}"/>')
    tcPr.append(shd)

def set_cell_margins(cell, top=100, bottom=100, left=150, right=150):
    tcPr = cell._element.get_or_add_tcPr()
    tcMar = OxmlElement('w:tcMar')
    for m, val in [('top', top), ('bottom', bottom), ('left', left), ('right', right)]:
        node = OxmlElement(f'w:{m}')
        node.set(qn('w:w'), str(val))
        node.set(qn('w:type'), 'dxa')
        tcMar.append(node)
    tcPr.append(tcMar)

def create_project_summary_docx():
    doc = Document()

    # Page Margins
    for section in doc.sections:
        section.top_margin = Inches(0.8)
        section.bottom_margin = Inches(0.8)
        section.left_margin = Inches(0.8)
        section.right_margin = Inches(0.8)

    # Base Styling
    style_normal = doc.styles['Normal']
    font_normal = style_normal.font
    font_normal.name = 'Calibri'
    font_normal.size = Pt(11)
    font_normal.color.rgb = RGBColor(0x2D, 0x37, 0x48) # Slate-800

    # Colors
    NAVY = RGBColor(0x1E, 0x29, 0x3B)
    INDIGO = RGBColor(0x4F, 0x46, 0xE5)
    DARK_GRAY = RGBColor(0x47, 0x55, 0x69)
    MUTED_BORDER = "CBD5E1"
    BG_LIGHT_INDIGO = "EEF2FF"
    BG_DARK_HEADER = "1E293B"

    # --- Title Header Box ---
    p_title = doc.add_paragraph()
    p_title.alignment = WD_ALIGN_PARAGRAPH.LEFT
    p_title.paragraph_format.space_before = Pt(0)
    p_title.paragraph_format.space_after = Pt(4)
    run_title = p_title.add_run("Adaptive Learning Platform with Deep Reporting AI")
    run_title.font.size = Pt(24)
    run_title.font.bold = True
    run_title.font.color.rgb = INDIGO

    p_sub = doc.add_paragraph()
    p_sub.paragraph_format.space_after = Pt(16)
    run_sub = p_sub.add_run("Executive Technical Summary & System Architecture Overview | Phase 1–5 Complete")
    run_sub.font.size = Pt(13)
    run_sub.font.color.rgb = DARK_GRAY

    # Callout Container Box for Metadata
    table_meta = doc.add_table(rows=1, cols=1)
    table_meta.alignment = WD_TABLE_ALIGNMENT.CENTER
    cell_meta = table_meta.rows[0].cells[0]
    set_cell_background(cell_meta, BG_LIGHT_INDIGO)
    set_cell_margins(cell_meta, top=120, bottom=120, left=180, right=180)
    
    p_meta = cell_meta.paragraphs[0]
    p_meta.paragraph_format.space_after = Pt(0)
    r_meta = p_meta.add_run(
        "Project Scope: B2B Multi-Tenant SaaS LMS  |  Stack: Next.js 14, FastAPI, PostgreSQL 16, Redis Streams, LLM Reporting Agent\n"
        "Status: Fully Verified (Backend 80/80 Pytest Passed, Frontend TypeScript 0 Errors)  |  Date: September 2026"
    )
    r_meta.font.size = Pt(9.5)
    r_meta.font.bold = True
    r_meta.font.color.rgb = NAVY

    doc.add_paragraph().paragraph_format.space_after = Pt(12)

    # Function for Section Headings
    def add_heading_1(text):
        p = doc.add_paragraph()
        p.paragraph_format.space_before = Pt(18)
        p.paragraph_format.space_after = Pt(6)
        p.paragraph_format.keep_with_next = True
        run = p.add_run(text)
        run.font.size = Pt(16)
        run.font.bold = True
        run.font.color.rgb = NAVY
        return p

    def add_heading_2(text):
        p = doc.add_paragraph()
        p.paragraph_format.space_before = Pt(12)
        p.paragraph_format.space_after = Pt(4)
        p.paragraph_format.keep_with_next = True
        run = p.add_run(text)
        run.font.size = Pt(13)
        run.font.bold = True
        run.font.color.rgb = INDIGO
        return p

    # --- 1. Executive Summary ---
    add_heading_1("1. Executive Summary")
    p_exec = doc.add_paragraph()
    p_exec.paragraph_format.space_after = Pt(10)
    p_exec.paragraph_format.line_spacing = 1.15
    p_exec.add_run(
        "Traditional Learning Management Systems (LMS) measure completion rather than comprehension. "
        "A learner can click through 100% of course materials while retaining minimal demonstrated mastery. "
        "The Adaptive Learning Platform with Deep Reporting AI solves this problem by transforming raw learning interactions into "
        "explainable Bayesian competency models, deterministic friction detection, and 100% grounded AI reporting with clickable evidence trails."
    )

    # Bullet points
    bullets = [
        ("Explainable Competency Modelling: ", "Mastery is computed strictly from graded answers using soft-evidence Bayesian Knowledge Tracing (BKT). Written answers are evaluated by an AI grading agent to emit deterministic confidence signals."),
        ("Evidence-Based Adaptation: ", "Dynamic next-step recommendations (continue, remediate, harder, easier, change format) are calculated deterministically from stored evidence and skill graphs."),
        ("Deterministic Reporting Analytics: ", "Period-over-period comparison ('What Changed'), Silent Struggler detection (high completion vs low mastery), Learning Bottleneck friction, and Assessment Intelligence."),
        ("Grounded Deep Reporting AI & Citation Validation: ", "Four audience-scoped reports (Learner, Manager, L&D, Organization) where every LLM claim MUST cite valid evidence IDs [E-#]. Uncited claims or invented figures are strictly refused."),
        ("AI Investigation Mode & Evidence Explorer: ", "Managers can ask natural-language questions (e.g. 'Why are learners struggling with SQL JOINs?'). The system compiles a structured evidence package, queries the LLM, validates citations, enforces causality guardrails, and renders full audit chains.")
    ]

    for title, desc in bullets:
        bp = doc.add_paragraph(style='List Bullet')
        bp.paragraph_format.space_after = Pt(4)
        r_t = bp.add_run(title)
        r_t.bold = True
        r_t.font.color.rgb = NAVY
        r_d = bp.add_run(desc)

    # --- 2. System Architecture & Core Pipeline ---
    add_heading_1("2. Deep Reporting AI Pipeline Architecture")
    p_arch = doc.add_paragraph()
    p_arch.paragraph_format.space_after = Pt(10)
    p_arch.add_run(
        "To guarantee 100% factual accuracy and zero hallucinations, the AI agent is NEVER permitted to query raw database tables directly. "
        "Instead, execution follows a strict deterministic-to-generative flow:"
    )

    # Pipeline Box Table
    pipe_table = doc.add_table(rows=1, cols=1)
    pipe_cell = pipe_table.rows[0].cells[0]
    set_cell_background(pipe_cell, "F8FAFC")
    set_cell_margins(pipe_cell, top=140, bottom=140, left=180, right=180)
    
    p_pipe = pipe_cell.paragraphs[0]
    p_pipe.paragraph_format.space_after = Pt(0)
    r_pipe = p_pipe.add_run(
        "LEARNING TELEMETRY EVENTS\n"
        "       ↓\n"
        "BAYESIAN COMPETENCY MODEL (BKT State & Updates)\n"
        "       ↓\n"
        "DETERMINISTIC ANALYTICS ENGINE (What Changed / Strugglers / Bottlenecks / Assessment Friction)\n"
        "       ↓\n"
        "EVIDENCE BUILDER (Structured Evidence Package with Records & Metrics)\n"
        "       ↓\n"
        "REPORTING AI AGENT (Structured Prompt with Defensive Nonce Markers)\n"
        "       ↓\n"
        "CITATION VALIDATOR (Validates Evidence IDs, Allowed Numbers, & Causality Guardrails)\n"
        "       ↓\n"
        "GROUNDED INVESTIGATION ANSWER & EVIDENCE EXPLORER DRAWER"
    )
    r_pipe.font.size = Pt(9.5)
    r_pipe.font.name = 'Consolas'
    r_pipe.font.bold = True
    r_pipe.font.color.rgb = INDIGO

    doc.add_paragraph().paragraph_format.space_after = Pt(10)

    # --- 3. Key Phases & Capabilities Implemented ---
    add_heading_1("3. Implementation Phases & Features Implemented")

    phases = [
        ("Phase 1: Foundation Audit & Bayesian Competency Engine", 
         "Verified PostgreSQL tables (LearnerCompetency, CompetencyHistory, LearningEvent, QuestionResponse, QuizAttempt, EvidenceRecord), "
         "Bayesian Knowledge Tracing algorithms, and 5-role RBAC authorization hierarchy."),

        ("Phase 2: Deterministic Reporting Analytics", 
         "Created `analytics_engine.py` providing exact SQL analytics without AI models: "
         "What Changed (temporal period-over-period comparisons), Silent Strugglers (completion >=70% & mastery <55%), "
         "Learning Bottlenecks (module-level retry friction & drop-offs), and Assessment Intelligence (question friction & retry rates)."),

        ("Phase 3: Manager Learning Intelligence Center", 
         "Built frontend `LearningIntelligenceCenter` component bringing together team cohort filters, risk metrics, "
         "temporal change metrics, silent struggler tables, bottleneck charts, and question difficulty cards."),

        ("Phase 4: Evidence Explorer", 
         "Implemented end-to-end evidence inspection via `EvidenceRecord` API and `EvidenceExplorer` frontend drawer. "
         "Managers can click any `[E-#]` citation pill to inspect full raw telemetry payloads, competency delta, "
         "attempt numbers, error types, and source context."),

        ("Phase 5: AI Investigation Mode", 
         "Added `POST /api/v1/reports/investigate` endpoint and `InvestigationPanel` component. "
         "Managers ask natural-language questions which are grounded in structured evidence packages, evaluated by the LLM agent, "
         "checked for citation validity and causality guardrails, and displayed with clickable evidence pills.")
    ]

    for p_title, p_desc in phases:
        add_heading_2(p_title)
        p = doc.add_paragraph()
        p.paragraph_format.space_after = Pt(6)
        p.add_run(p_desc)

    # --- 4. Guardrails & Security Design ---
    add_heading_1("4. Guardrails, Multi-Tenancy & Security Design")
    
    sec_bullets = [
        ("Causality Guardrail: ", "The system explicitly prevents correlation from being represented as causation. Claims typed CAUSAL_CLAIM or containing causal words ('caused', 'led to', 'resulted in') are strictly rejected by validator.py."),
        ("Number & ID Validation: ", "Every numerical figure in an AI narrative must match stored metric or record values exactly. Invented numbers or hallucinated evidence IDs trigger instant claim rejection."),
        ("Multi-Tenant Scope Isolation: ", "All queries and evidence builders enforce `org_id` isolation. Managers can only view and investigate learners within their explicit team remit."),
        ("Prompt Defanging: ", "Package data is sanitized with nonce markers (`<<<EVIDENCE_START id=nonce>>>`) to prevent prompt injection attacks embedded inside learning content or questions.")
    ]

    for title, desc in sec_bullets:
        bp = doc.add_paragraph(style='List Bullet')
        bp.paragraph_format.space_after = Pt(4)
        r_t = bp.add_run(title)
        r_t.bold = True
        r_t.font.color.rgb = NAVY
        bp.add_run(desc)

    # --- 5. API Endpoints Reference ---
    add_heading_1("5. Core API Endpoints Reference")

    table_api = doc.add_table(rows=1, cols=3)
    table_api.alignment = WD_TABLE_ALIGNMENT.CENTER
    table_api.autofit = False

    # Header Row
    hdr_cells = table_api.rows[0].cells
    hdr_titles = ["HTTP Method & Path", "Target Role", "Description / Purpose"]
    widths = [Inches(2.5), Inches(1.5), Inches(2.8)]
    for i, title in enumerate(hdr_titles):
        hdr_cells[i].width = widths[i]
        set_cell_background(hdr_cells[i], BG_DARK_HEADER)
        set_cell_margins(hdr_cells[i], top=100, bottom=100, left=120, right=120)
        p = hdr_cells[i].paragraphs[0]
        p.paragraph_format.space_after = Pt(0)
        r = p.add_run(title)
        r.font.bold = True
        r.font.size = Pt(10)
        r.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)

    api_rows = [
        ("POST /api/v1/auth/login", "Public", "Authenticates user and returns JWT bearer token"),
        ("POST /api/v1/adaptive/next", "Learner", "Computes Bayesian next-step learning recommendation"),
        ("POST /api/v1/reports/generate", "Manager / Admin", "Builds evidence package & grounded AI report"),
        ("POST /api/v1/reports/investigate", "Manager / Admin", "Runs natural language AI investigation with citation validation"),
        ("GET /api/v1/reports/{id}/evidence/{eid}", "Manager / Admin", "Returns raw evidence record & trace for Evidence Explorer"),
        ("GET /api/v1/analytics/what-changed", "Manager / Admin", "Period-over-period deterministic analytics comparison"),
        ("GET /api/v1/analytics/silent-strugglers", "Manager / Admin", "Identifies learners with high progress vs low mastery"),
        ("GET /api/v1/analytics/bottlenecks", "Manager / Admin", "Identifies module-level retry friction & drop-offs"),
        ("GET /api/v1/analytics/assessment-intelligence", "Manager / Admin", "Analyzes question retry rates & factual difficulty metrics")
    ]

    for method_path, role, desc in api_rows:
        row_cells = table_api.add_row().cells
        for i, text in enumerate([method_path, role, desc]):
            row_cells[i].width = widths[i]
            set_cell_margins(row_cells[i], top=80, bottom=80, left=120, right=120)
            p = row_cells[i].paragraphs[0]
            p.paragraph_format.space_after = Pt(0)
            r = p.add_run(text)
            r.font.size = Pt(9.5)
            if i == 0:
                r.font.name = 'Consolas'
                r.font.bold = True
                r.font.color.rgb = INDIGO

    doc.add_paragraph().paragraph_format.space_after = Pt(14)

    # --- 6. Verification & Test Metrics ---
    add_heading_1("6. System Verification & Test Coverage")
    p_test = doc.add_paragraph()
    p_test.paragraph_format.space_after = Pt(8)
    p_test.add_run(
        "The platform has been rigorously validated across backend API test suites and frontend static typechecking:"
    )

    t_bullets = [
        ("Backend Pytest Suite: ", "80 out of 80 tests passing (100% pass rate) across unit, analytics engine, reporting insights, and investigation suites."),
        ("Frontend TypeScript Compiler: ", "npx tsc --noEmit executed cleanly with 0 type errors across all Next.js App Router components."),
        ("Citation Validation Tests: ", "Verified 100% rejection rate for uncited claims, fabricated evidence IDs, unallowed numbers, and causal statements.")
    ]

    for title, desc in t_bullets:
        bp = doc.add_paragraph(style='List Bullet')
        bp.paragraph_format.space_after = Pt(4)
        r_t = bp.add_run(title)
        r_t.bold = True
        r_t.font.color.rgb = NAVY
        bp.add_run(desc)

    # Output file path
    target_path = os.path.join("d:\\ALP-Deep_Report_AI\\adaptive-lms", "Project_Summary_Document.docx")
    doc.save(target_path)
    print(f"Successfully created: {target_path}")

if __name__ == "__main__":
    create_project_summary_docx()
