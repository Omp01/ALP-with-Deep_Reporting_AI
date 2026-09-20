# Learning Experience (Phase 2)

The learner-facing product: Home, Explore, Course Detail, My Learning, the Course Player and Assessments. Everything on these screens is read from stored data; a value that cannot be known is empty and the screen says so.

## Screens

| Route | What it shows | Data source |
|---|---|---|
| `/learner/dashboard` (Home) | Continue learning, stats, recommendations with reasons, competencies, recent activity, latest AI insight, in-progress courses | `GET /learning/home` |
| `/explore` | Catalog with search, category, difficulty, sort; skill tags; progress on enrolled courses | `GET /courses` |
| `/courses/{id}` | Objectives, modules and items, competencies developed with the learner's mastery, prerequisites and whether they are met, progress, Enrol / Continue | `GET /learning/courses/{id}` |
| `/learner/learning?course_id=&item_id=` | The player: lesson, outline, previous/next, course progress | `GET /learning/content/{id}` + the overview |
| `/learner/my-learning` | Enrolled courses with derived progress | `GET /courses` |
| `/learner/assessments` | Quizzes across enrolled courses, opening each in the player | `GET /quizzes/learner/summary` |

Nav items still marked *planned* (Learning Paths, Progress, Competencies, Profile, Learning History) have no page yet.

## Home: where each number comes from

| Element | Derivation |
|---|---|
| Continue learning | The enrolled, unfinished course with the most recent activity; the item is the resume point (below) |
| Stats | Enrolled courses, **completed courses (derived from lesson records)**, completed lessons, total credited learning time |
| Recommended | Rule-based and explained, never generated. (1) For each competency with mastery below 60%, weakest first, the first unfinished video/reading mapped to it through `content_competencies`; reason: *"Your SQL Joins mastery is 42%, and this covers it."* (2) Remaining slots: published courses not enrolled in, most enrolled first; reason states the enrolment count or "not started" |
| Competencies | `learner_competencies` rows: mastery, and the number of answers behind it |
| Recent activity | `learning_events` of the kinds that read naturally (started/completed lesson, assessment started/finished, assignment submitted) |
| AI insight | The learner's newest stored `ai_insights` row, trimmed; an empty state when none exists. Nothing is generated on this page |

> **Caveat until Phase 5.** The mastery numbers shown are whatever the current adaptive engine wrote. That engine still has the defects listed in `PRODUCT_AUDIT.md` (C1–C10), notably that quiz answers are read as correct. The screens display those values faithfully; they will become trustworthy when the competency engine is rebuilt.

## Progress is derived

Course progress = completed lesson items ÷ published lesson items, computed from `content_progress` (`app/services/progress.py`). `enrollments.progress_pct` is only a cache, rewritten from that result whenever progress changes. `PUT /enrollments/{id}/progress` can no longer set a number: it recomputes, and may only drop or re-activate an enrollment. Migration 004 corrected stored values that no lesson records supported (an earlier demo script had marked a learner's course "completed" with no lessons completed).

### Who may complete what

| Item type | Completed by |
|---|---|
| Video, audio, reading, document | The player: real playback reached 90 % (or the video ended past 85 %), a reading scrolled to the end after enough time, or the learner marked it done |
| Quiz | The server, when a submitted attempt passes. A client report of "completed" is ignored and capped below the threshold |
| Assignment | The server, on submission (the grade arrives later) |

### Time spent is not inflatable

The client counts seconds only while the learner is engaged (video playing, lesson open) **and** the tab is visible, and reports them in heartbeats every 15 s. The server independently credits at most 60 s per report and never more than the wall-clock time since the previous report. Quiz time is the measured interval between starting and submitting an attempt.

### Watch progress

Video progress advances only by time that actually played (a natural step of ≤ 2.5 s between readings). Scrubbing to the end adds nothing. It builds on the percent already saved, so resuming continues rather than restarting. The resume position is stored (`content_progress.position_seconds`) and the player starts there.

### Where the learner picks up

`choose_resume`: the most recently touched in-progress item, else the first item not yet completed, else none (course finished).

## The player

`components/player/` (outline, lesson view) and `components/content/` (renderers). `ContentRenderer` chooses a renderer from what the API says the item is; nothing is specific to a course.

| Item | Renderer | Notes |
|---|---|---|
| YouTube video | `YouTubePlayer` | Official IFrame API via `youtube-nocookie.com`; states drive tracking. If the video is removed or embedding is disabled it says so, links to YouTube, and offers "I watched it there" |
| Direct video / audio URL | `MediaPlayer` | Native controls, resume, tracked the same way |
| Uploaded file | `MediaPlayer` / `DocumentViewer` | Fetched through the authenticated `/learning/content/{id}/file` and shown from an object URL. PDFs render inline; other formats offer a download plus extracted text |
| Reading | `ArticleViewer` + `Markdown` | Safe Markdown renderer (no `dangerouslySetInnerHTML`). Auto-completes at the end of the text only after ≥ 40 % of the estimated reading time; a manual "Mark as complete" always works |
| Quiz | `QuizRenderer` | Multiple choice, timer, in-app confirmation for unanswered questions, graded review with explanations. Answers are never sent to the browser before grading |
| Assignment | `AssignmentRenderer` | Instructions, rubric, a real submission form, submission status, score and feedback once graded, revisions |

The outline shows every module and item with completion state and lengths; on screens below 1024 px it opens as a drawer.

**Media resolution** (`app/services/media.py`) is one pure, unit-tested function. It accepts only well-formed 11-character YouTube ids from recognised hosts and `http(s)` direct-media URLs; anything else resolves to no media instead of being handed to the browser.

## Visibility

Learners see **published** courses and items only; authors (L&D admin, org admin) may preview drafts, flagged as *Preview*. A draft course or item is a 404 to a learner, and progress cannot be recorded against it.

## API

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/v1/learning/home` | Learner home |
| GET | `/api/v1/learning/courses/{id}` | Overview: objectives, competencies, prerequisites, modules, progress |
| GET | `/api/v1/learning/content/{id}` | Player payload: item, media, progress, previous/next |
| GET | `/api/v1/learning/content/{id}/file` | Authenticated stream of an uploaded file |
| POST | `/api/v1/progress/content/{id}` | Report lesson progress (rules above) |
| GET | `/api/v1/progress/course/{id}` | Derived progress with a per-item map |
| POST | `/api/v1/assignments/{id}/submit` | Hand in work (path is authoritative; text or URL required) |

Every one is tenant-scoped and returns 404 for another tenant's resource; see `MULTI_TENANCY.md`.

## Events produced so far

Only what the server can vouch for: `content_started` (first report on an item) and `content_completed` (once), each with `content_id`, course and module, plus the existing assessment events. Client-side video events (paused, resumed, and so on) and learning sessions belong to Phase 4, when the event vocabulary is defined once.

## Known limits

- **Not verified against live YouTube.** The build environment had no outbound internet, so the YouTube iframe's presence and URL were verified in a real browser, but actual playback and the IFrame API's state events were not. Uploaded-file playback and the PDF viewer were also not exercised in a browser (the file endpoint needs MinIO).
- Uploaded files are returned whole (no HTTP range requests), which is unsuitable for large videos.
- Content created by the ingestion endpoint is published immediately; the review step arrives with Phase 3.
- Only multiple-choice questions render. Short-answer, open-ended and coding items need the grading agent (Phase 5).
- The seed's learner history (Alice's progress, quiz attempts, events) is inserted directly rather than produced through these APIs, and contains some duplicate events, so it appears twice in Recent activity. A demo driver that plays the journey through the real endpoints is planned with Phases 4–6.
- The greeting uses the browser's clock.
