# Content Model

```text
Organization ─┬─ Course ── Module ── ContentItem ── ContentChunk
              │                          │ └─ ContentCompetency ── Competency ── (prerequisites)
              │                          └─ ContentProgress (per learner)
              └─ Competency, CourseCompetency, ModuleCompetency
```

Every row carries `org_id`. Course → Module → ContentItem is generic: nothing in the model knows about any particular course, so any content ingested later flows through the same structure.

## Course

| Field | Notes |
|---|---|
| `status` | `draft`, `published`, `archived` |
| `category`, `difficulty` | filter facets for Explore |
| `instructor_id`, `created_by_id` | authorship |
| `rating` | **NULL.** There is no ratings source yet; the UI hides it. Migration 003 cleared the placeholder 4.8 that revision 002 gave every course |
| `duration_minutes` | Optional author override. When NULL the API **computes** it: sum of content `duration_seconds`, rounded up; NULL if nothing is timed |
| `enrollment_count` | Computed per request from `enrollments`; drives the "Most enrolled" sort (previously "popular" sorted by the fake rating) |

Derived fields are built in one place, `build_course_response()` in `api/v1/courses.py`, so list, detail, create, update and publish agree.

## ContentItem

| Field | Notes |
|---|---|
| `content_type` | Stored upper-case: `VIDEO`, `ARTICLE`, `QUIZ`, `ASSIGNMENT`, `DOCUMENT`, `TEXT`. The API upper-cases on write |
| `status` | Lifecycle, DB-checked: `draft` → `processing` → `review` → `published`; or `failed` |
| `source_type` | Where it came from: `authored`, `upload`, `youtube`, `url` |
| `source_url` | Original URL for `youtube` / `url` sources |
| `content_url` | What the player loads (embed URL, storage key) |
| `text_content` / `raw_text` / `transcript` | Authored text, extracted text, transcript |
| `duration_seconds` | Real length, used for course duration |
| `analysis` (JSON) | Output of content analysis: summary, level, learning objectives, concepts, and competency **decisions** (`link` / `create` / `skip`), plus provenance (provider, model, prompt version) and rejected-question notes. Written by the ingestion pipeline, editable by the admin. NULL until analysed |
| `content_hash` | SHA-256 of the file or of the extracted/transcribed text; drives duplicate detection and the analysis cache |
| `chunk_count`, `metadata` | Ingestion bookkeeping; `metadata` also carries `transcript_source`, warnings, video author, quiz item link |

**Lifecycle.** Ingestion creates items as `processing` and moves them to `review` when the pipeline has finished (successfully or with something to fix); an administrator then publishes them. Failed items are `failed`. **Learner-facing queries show `published` only**, so nothing ingested reaches a learner until it is approved and published (Phase 3). See [CONTENT_INGESTION.md](CONTENT_INGESTION.md).

### Ingestion tables (Phase 3)

| Table | Purpose |
|---|---|
| `ingestion_jobs` | One row per item's processing history: `source_type`, `source_url`, `content_item_id`, `status` (`pending`, `processing`, `ready_for_review`, `needs_attention`, `failed`, `completed`; DB-checked), `stage`, `stages` (JSON per-stage log), `error_code`, `attempts`, timestamps |
| `question_candidates` | AI-drafted or hand-written questions awaiting review: text, options `[{id,text,is_correct}]`, explanation, difficulty, `competency_id`/`competency_name`, **`source_quote`**, `origin` (`generated`/`manual`), `status` (`pending`/`approved`/`rejected`/`published`), `edited`, `published_question_id`. Tenant-safe composite FK to the content item |
| `content_chunks.embedding_model` | Name of the model that produced a chunk's embedding, so vectors from different models are never compared |

Publishing turns approved candidates into `quizzes` / `quiz_questions` / `quiz_options` and a QUIZ lesson item linked through `quizzes.content_item_id`; the link is remembered in `content_items.metadata.quiz_content_item_id`, so republishing appends to the same quiz.

`POST /modules/{id}/content` now persists every supplied field and sets `course_id` from the module. Before Phase 1 it silently dropped description, text, duration, order and status, and left `course_id` empty.

## Quizzes and assignments are lesson items

A quiz or assignment appears in a course outline as a content item of type `QUIZ` / `ASSIGNMENT`. That link is an explicit, unique foreign key: `quizzes.content_item_id` and `assignments.content_item_id` (partial unique indexes, at most one per item). It replaces a JSON hint in `content_items.metadata` and, in the old quiz handler, a guess by title substring. Passing a quiz or submitting an assignment completes exactly that item (`app/services/progress.py`).

`content_progress` is tenant-owned (`org_id`), unique per learner and item, and stores a resume `position_seconds` for videos.

## Media

How an item is presented is decided by one pure function (`app/services/media.py`) from `source_type`, `content_url` and `source_url`: a YouTube id (`youtube`), a direct `http(s)` video/audio URL, or an uploaded file streamed through the authenticated `/learning/content/{id}/file`. Seeded videos are real YouTube videos, each verified through YouTube's oEmbed endpoint. Their length is stored as 0 (unknown) because the platform does not yet read it from YouTube; readings carry an estimated reading time (200 words per minute), recorded in `metadata.duration_basis`.

Canonical content types written by ingestion are now `DOCUMENT`, `AUDIO` and `VIDEO` (previously lower-case `document/audio/video/slide`), and ingested items get their `course_id` (they used to be created without one, which broke course counts).

## Competency mapping

- `course_competencies` — target mastery per course.
- `module_competencies` — weight per module.
- `content_competencies` — which competencies a content item develops (finest grain; used by adaptive selection from Phase 6).
- `quiz_questions.competency_id` — what a question assesses.

Selection logic reads these tables. It never branches on a course's name or code.

## Known gaps (scheduled)

| Gap | Phase |
|---|---|
| ~~Video length is unknown for YouTube items until the player reports it~~ | **Fixed in Phase 3** (read from the watch page; left unknown, never guessed, if the page cannot be read) |
| ~~`content_chunks.embedding` is a JSON column; no code computes embeddings~~ | **Fixed in Phase 3** (optional stage; vectors stored with their model name; still JSON, a pgvector column is a later optimisation; nothing retrieves by them until Phase 7) |
| ~~Ingestion produces a fake transcript for audio/video~~ | **Fixed in Phase 3** (real transcription with `faster-whisper` if installed, otherwise an honest "unavailable" and a manual transcript) |
