# AI provider abstraction

The platform never depends on a vendor. Everything that needs a language model asks for an `AIProvider` (`shared/schemas/ai_provider.py`) and gets whichever one the environment selects. Switching from a local model to a hosted one is a configuration change, not a code change.

```
ingestion pipeline ─┐
(later) grading     ├─► app/ingestion/ai.py ─► AIProvider ─► Ollama | Gemini | Groq | any OpenAI-compatible server
(later) reporting  ─┘        │
                             └─ structured output: JSON schema validation + one repair retry
```

## Choosing a provider

Set `AI_PROVIDER` in `.env`:

| `AI_PROVIDER` | Runs | Cost | Needs | Notes |
|---|---|---|---|---|
| `ollama` | On your machine | **Free** | [Ollama](https://ollama.com) with a model pulled | The zero-cost path. No data leaves the machine. See [ZERO_COST_MODE.md](ZERO_COST_MODE.md). |
| `openai_compatible` | Anywhere | Depends | `AI_BASE_URL` (+ `AI_API_KEY` if the server wants one) | Covers OpenAI, Together, vLLM, LM Studio, llama.cpp server, Azure-style gateways… |
| `gemini` | Google | Free tier exists | `GEMINI_API_KEY` | External: content is sent to Google. |
| `groq` | Groq | Free tier exists | `GROQ_API_KEY` | External: content is sent to Groq. |
| `none` | — | — | — | AI stages are reported as unavailable. Nothing is faked. |

Models:

| Variable | Meaning |
|---|---|
| `OLLAMA_BASE_URL` (default `http://127.0.0.1:11434`) | Where Ollama listens. From inside Docker on Windows use `http://host.docker.internal:11434`. |
| `OLLAMA_MODEL` (default `llama3.1`) | Model used for every task when `AI_PROVIDER=ollama`. |
| `AI_MODEL` (default `gpt-4o-mini`) | Model for `openai_compatible`. |
| `GEMINI_MODEL`, `GROQ_MODEL` | Model for those providers. |
| `AI_MODEL_ANALYSIS`, `AI_MODEL_QUESTIONS`, `AI_MODEL_GRADING` | **Per-task override** for any provider. Lets a small fast model extract objectives while a stronger one writes questions or grades written answers (`docs/GRADING_AGENT.md`; grading uses temperature 0). Empty = the provider default above. Learner answers are sent to the configured provider for grading: use a local model if they must not leave the deployment. |
| `AI_TIMEOUT_SECONDS` (30), `AI_MAX_RETRIES` (3) | Per request. Ollama gets at least 120 s because local models on a CPU are slow. |
| `AI_EMBEDDING_MODEL` | Optional. Enables the embedding stage using the same server (an OpenAI-compatible `/embeddings` endpoint; for Ollama, e.g. `nomic-embed-text`). Empty = the stage is skipped. |

The admin's **Add Content** page reads `GET /api/v1/admin/content/capabilities` and says plainly when no provider is configured, before anyone uploads.

## Contract

```python
class AIProvider:
    async def complete(self, request: AICompletionRequest) -> AICompletionResponse: ...
    async def health_check(self) -> bool: ...
    @property
    def provider_name(self) -> str: ...
```

A provider raises `AIProviderError` for anything it cannot recover from (after its own retries). The ingestion layer turns that into an `ai_unavailable` failure recorded on the job, with the provider's message (URLs and library documentation links are stripped for display). There is **no fallback provider and no canned answer**: if the model is down, the job says so and can be retried.

## Structured output

`complete_structured(task, system, user, schema)` in `app/ingestion/ai.py`:

1. asks for JSON (`response_format: json_object`, temperature 0.2);
2. extracts the JSON object even from a fenced or chatty reply;
3. validates it with a Pydantic model; coercing validators normalise the harmless variations models produce (a level of `"Beginner"`, a difficulty of `"0.7"`, a correct answer given as a letter);
4. on invalid output, **one** repair request that quotes the error; then `ai_output_invalid`.

The exact prompts and their version (`ingestion_v1`) are in `app/ingestion/prompts.py`. The version is stored with every analysis so a result can be traced to the prompt that produced it, and it is part of the cache key: changing a prompt re-analyses content instead of serving stale output.

## What is recorded

Each analysis stores `provenance` (provider name and model, attempts) and `prompt_version`. The review page shows "Drafted by ollama (llama3.1)", so an administrator always knows a proposal came from a model, and which one.

## Choosing a model

Not verified here (see the limits in [CONTENT_INGESTION.md](CONTENT_INGESTION.md)); guidance, not measurement:

- Question drafting needs reliable JSON and faithful quoting. Instruction-tuned models of roughly 7–8B parameters (e.g. `llama3.1`, `qwen2.5`) usually manage; smaller ones tend to fail the grounding check often. That failure is visible ("N rejected") rather than silent, so you will know.
- If the rejection count is high, raise `AI_MODEL_QUESTIONS` to a stronger model before lowering any check.
- Long documents are sampled (`INGESTION_MAX_ANALYSIS_CHARS`, default 12,000 characters per call), so context length is rarely the limit.

## Adding a provider

Implement `AIProvider`, add a branch in `provider_for` and `ai_status` (`app/ingestion/ai.py`), and document its variables here. Nothing else changes. Tests replace the provider with a scripted double through `set_provider_override`; they never call a real model.

## Notes from running against a real Gemini key

- `AI_MODEL_CHECKIN` (with `AI_MODEL_ANALYSIS`, `AI_MODEL_QUESTIONS`, `AI_MODEL_GRADING`, `AI_MODEL_REPORTING`) is a per-task model. Each provider uses **its own** model setting (`GEMINI_MODEL`, `GROQ_MODEL`, `OLLAMA_MODEL`) unless a task override is set; `AI_MODEL` applies only to an OpenAI-compatible endpoint. Before this was fixed, `AI_MODEL=gpt-4o-mini` was sent to Gemini.
- Google retires model names (`gemini-1.5-flash` and `gemini-2.5-flash` are unavailable to new keys). List what your key can use with `GET https://generativelanguage.googleapis.com/v1beta/models` and the `x-goog-api-key` header. The default is now `gemini-3.5-flash`.
- Gemini 2.5 and later "think" first and thinking tokens count against `maxOutputTokens`; the provider adds headroom for those models so JSON answers are not cut off.
- The Gemini free tier allows about **20 requests per day per model**. A daily-quota error (`429`, `PerDay`) is not retried and the message says so. Give heavy tasks their own model (the check-in uses three calls per login), use a billed key, or use a local model.
- The API key is sent in the `x-goog-api-key` header, not in the URL, so it does not appear in request logs.
