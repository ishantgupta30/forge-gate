# Forge Gate

**The approval pipeline for AI-generated game assets.**

Forge Gate generates game character assets across AI providers using
Genblaze, then automatically enforces the studio's own approval rules —
style consistency and duplicate detection — before anything reaches
production. Only approved assets ship; everything else retries with a
specific, visible prompt correction, or escalates to human review after 3
attempts.

## Providers & models used
- **GMI Cloud** — `seedream-5.0-lite` (primary), `flux-kontext-pro` (fallback)
- Swap in a second real provider (Replicate/OpenAI/etc.) once you have keys —
  see `backend/pipeline.py`

## How this uses Genblaze
`backend/pipeline.py` runs generation through a single `Pipeline().step()`
call with `fallback_models=[...]`, so Genblaze automatically retries on
`MODEL_ERROR` across providers. Each retry attempt within a job is chained
via `Pipeline.from_result(previous_result)`, so every attempt's manifest
carries a `parent_run_id` back to the one before it — that's what makes the
attempt timeline (`GET /jobs/{id}/timeline`) trivial: it's just a walk of a
linked chain, not a bespoke versioning system.

## How this uses Backblaze B2
`backend/storage.py` wires every Genblaze run to
`ObjectStorageSink(S3StorageBackend.for_backblaze(...))`. Every asset AND
its SHA-256 provenance manifest land in B2 automatically. Our own database
(`backend/models.py`) then classifies each B2 object as one of:
**reference** (studio style guide/exemplars) / **candidate** (every
generation attempt) / **approval record** (final decision + full retry
history) — so B2 is the permanent audit trail of the approval process, not
just a bucket of images.

## Setup
1. Copy `.env.example` to `.env` and fill in:
   - Backblaze B2: sign up free at backblaze.com/cloud-storage, create a
     bucket, generate a key → `B2_KEY_ID` / `B2_APP_KEY` / `B2_BUCKET`
   - GMI Cloud: sign up + submit the hackathon credits form → `GMICLOUD_API_KEY`
2. `pip install -r requirements.txt`
3. `uvicorn backend.main:app --reload`
4. `POST /jobs` with `{"studio_id": "...", "prompt": "..."}` to run a job end to end.
5. `GET /jobs/{job_id}/timeline` to see every attempt, prompt, and check result.

## What's stubbed vs. real
- **Real**: Genblaze pipeline call, B2 sink, fallback config, DB schema,
  retry/decision loop, FastAPI endpoints.
- **Stubbed — must be filled in before demo**:
  - `backend/critic.py :: embed_image()` — plug in a real embedding model
    (CLIP or a GMI Cloud embedding endpoint) for duplicate detection.
  - Reference asset upload endpoint (`ReferenceAsset` model exists; no route
    yet) — needed so studios can actually upload a style guide before Step 1.
  - `backend/critic.py :: check_style_consistency()` uses a placeholder
    vision model name (`qwen-vl`) — confirm the exact model slug GMI Cloud
    exposes for vision-capable chat before relying on it.

## Note on unverified API details
`backend/pipeline.py` assumes attribute names like `result.run.run_id`,
`result.run.parent_run_id`, and `step.model` based on documented Genblaze
usage patterns. Confirm these exact field names against
`docs/features/iteration.md` and `docs/features/object-storage.md` in the
[Genblaze repo](https://github.com/backblaze-labs/genblaze) once you can run
it locally — some may differ slightly by SDK version.
