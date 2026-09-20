# Zero-cost mode

Everything in the content pipeline can run on your own machine with no paid service, no API key and no data leaving it. This page is the setup, and an honest account of what you give up.

## What is free

| Need | Free option | Paid / external alternative |
|---|---|---|
| Language model (analysis, questions) | **Ollama** running locally | Gemini, Groq, OpenAI-compatible hosts |
| Object storage | the bundled `services/s3-storage` (files on a Docker volume) | S3 / MinIO |
| Database, cache | PostgreSQL and Redis containers | managed services |
| Transcription of uploaded audio/video | `faster-whisper` (optional, CPU) | — |
| Transcripts for YouTube | the video's own captions (fetched from YouTube) | — |
| Embeddings | Ollama `nomic-embed-text` (optional) | hosted embeddings |

## Setup (Windows, PowerShell)

### 1. Install Ollama and pull a model

Install from <https://ollama.com>, then:

```powershell
ollama pull llama3.1            # ~4.7 GB; any instruction-tuned model that can return JSON will do
ollama pull nomic-embed-text    # optional: enables the embedding stage
```

### 2. Point the platform at it

In `.env`:

```dotenv
AI_PROVIDER=ollama
OLLAMA_BASE_URL=http://host.docker.internal:11434   # API running in Docker
# OLLAMA_BASE_URL=http://127.0.0.1:11434            # API running directly on Windows
OLLAMA_MODEL=llama3.1
AI_EMBEDDING_MODEL=nomic-embed-text                 # optional; leave empty to skip embeddings
AI_TIMEOUT_SECONDS=120
```

Use a larger model only for the step that needs it:

```dotenv
AI_MODEL_QUESTIONS=qwen2.5:14b
```

### 3. Allow the file types

If your `.env` was created before Phase 3 it probably restricts uploads to `pdf,pptx,ppt,docx,doc,mp3,mp4`, which **rejects `.txt` and `.md`**. Replace it (and remove `ppt`/`doc`, which cannot be read):

```dotenv
ALLOWED_FILE_TYPES=pdf,docx,pptx,txt,md,mp4,webm,mov,mp3,wav,m4a
```

### 4. Rebuild the storage container

Phase 3 fixed a serious hole in `services/s3-storage` (it accepted unauthenticated requests and path traversal). A container built earlier still has it:

```powershell
docker compose up -d --build minio
```

The service now requires a bearer token (`STORAGE_TOKEN`, default: `MINIO_SECRET_KEY`); the API sends it automatically.

### 5. Apply the migration and restart

```powershell
$env:DATABASE_URL_SYNC = "postgresql://adaptive_lms:adaptive_lms_dev_password@127.0.0.1:5433/adaptive_lms"
python -m alembic -c database\alembic.ini upgrade head     # to 005_content_ingestion
```

Restart the API. The Add Content page will show whether a provider is configured.

### 6. Optional: transcribe uploaded recordings locally

```powershell
pip install faster-whisper      # CPU; the first use downloads the model named by WHISPER_MODEL
```

```dotenv
WHISPER_MODEL=base              # tiny | base | small | medium ; larger = slower and more accurate
```

Without it, an uploaded video or audio file is still stored and playable, and the admin is asked to paste a transcript.

## What you give up

- **Speed.** A 7–8B model on a CPU can take minutes per document (two model calls). The job page shows progress; the API stays responsive because processing is in the background.
- **Quality varies with the model.** Small models fail the grounding check more often ("N rejected by verification") and write plainer distractors. The design makes this visible instead of hiding it; if it bites, use a larger model for `AI_MODEL_QUESTIONS`, and always review before approving.
- **Automatic transcription** of uploaded media needs `faster-whisper` and time; YouTube captions (free, instant) are the better source when they exist. Automatic YouTube captions are flagged as lower quality.
- **No OCR.** Scanned PDFs cannot be read at all in either mode; the job says so.
- **YouTube needs internet** from the API host (to read the captions). A fully offline install can still use uploaded files.

## Running without any AI

`AI_PROVIDER=none` is a legitimate mode. Content can be uploaded and read (text extraction, chunking) and published; objectives, competencies and questions are then entered by hand in the review page. The platform never substitutes generated-looking filler.

## Cost of the paid alternatives

Not estimated here: prices and free-tier limits change. If you use Gemini or Groq, set the key, set `AI_PROVIDER`, and note that document text is sent to that provider, which matters for confidential training material.
