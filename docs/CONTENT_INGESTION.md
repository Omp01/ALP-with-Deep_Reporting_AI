# Content Ingestion Architecture & Pipeline

> **Adaptive LMS with Deep Reporting AI**  
> Multi-Format Ingestion, S3 Persistence, Text Extraction, and Semantic Chunking Specification.

---

## 1. Pipeline Overview

```mermaid
sequenceDiagram
    autonumber
    actor Instructor as Instructor / Admin
    participant API as API Gateway (/ingestion)
    participant S3 as S3-Compatible Storage
    participant DB as PostgreSQL Database
    participant Parser as TextExtractor & Chunker

    Instructor->>API: POST /ingestion/upload (multipart file)
    API->>S3: PUT /{org_id}/{job_id}_{filename}
    API->>DB: INSERT INTO ingestion_jobs (status="pending")
    API-->>Instructor: 201 Created (job_id, storage_path)

    Instructor->>API: POST /ingestion/jobs/{id}/process
    API->>DB: UPDATE ingestion_jobs (status="processing")
    API->>S3: GET /{storage_path}
    S3-->>API: file_bytes
    API->>Parser: extract_from_bytes(file_bytes, filename)
    Parser-->>API: raw_text, structural_metadata
    API->>Parser: chunk_text(raw_text, target_size=350, overlap=50)
    Parser-->>API: chunks_list
    API->>DB: INSERT INTO content_items
    API->>DB: INSERT INTO content_chunks (chunk_index, text, token_count)
    API->>DB: UPDATE ingestion_jobs (status="completed", result_summary)
    API-->>Instructor: 200 OK (character_count, chunk_count, content_item_id)
```

---

## 2. Supported Formats & Parsing Strategies

| Format | Extensions | Parser Engine | Extraction Strategy & Metadata Extracted |
| :--- | :--- | :--- | :--- |
| **PDF Documents** | `.pdf` | PyMuPDF (`fitz`) / `pypdf` | Multi-page text streams, page count, formatting preservation. |
| **Word Documents** | `.docx`, `.doc` | `python-docx` | Structured paragraph ordering, embedded tables text extraction. |
| **PowerPoint Presentations** | `.pptx`, `.ppt` | `python-pptx` | Slide-by-slide shape traversal, speaker notes, titles. |
| **Audio & Video Assets** | `.mp3`, `.mp4`, `.wav`, `.m4a` | OpenAI Whisper / Speech Pipeline | Timecoded speech-to-text transcript segments. |
| **Plain Text & Markdown** | `.txt`, `.md`, `.markdown` | Python UTF-8 stream | Native character stream extraction, heading tags. |

---

## 3. Semantic Chunking Strategy

Documents are processed using `SemanticChunker`:
- **Target Chunk Size:** 350 tokens (~270 words).
- **Chunk Overlap:** 50 tokens (~38 words) to maintain semantic continuity across chunk boundaries.
- **Boundary Preservation:** Chunks honor paragraph breaks (`\n\n`) and sentence boundaries before resorting to word-level splits.
- **Storage Target:** Persisted in `content_chunks` table linked to parent `content_items` with indexed `(content_item_id, chunk_index)`.

---

## 4. Ingestion Job Lifecycle

```mermaid
stateDiagram-v2
    [*] --> pending: POST /upload (S3 binary stored)
    pending --> processing: POST /jobs/{id}/process
    processing --> completed: Successful extraction & chunking
    processing --> failed: Corrupted file or extraction error
    completed --> [*]
    failed --> [*]
```

---

## 5. Security & Isolation Guarantees

1. **Tenant-Scoped Storage Paths:** S3 objects are isolated under `{org_id}/{job_id}_{filename}` prefixes.
2. **Access Control:** Content upload and processing endpoints strictly require `instructor` or `org_admin` roles. Standard learners attempting uploads receive `403 Forbidden`.
3. **Audit Trails:** All ingestion operations write compliance audit entries to `audit_logs` (`CONTENT_FILE_UPLOADED`).
