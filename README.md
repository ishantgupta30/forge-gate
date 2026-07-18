# Forge Gate

**The approval pipeline for AI-generated game assets.**

Forge Gate generates game assets from a text prompt, runs them through a real
AI critic checked against a studio's own style guide and prior approved work,
and automatically retries or escalates to human review — so nothing gets
approved without a reason attached to it, and every generation is provenance-
tracked back to the exact run that produced it.

**Live demo:** [forgegate.netlify.app](https://forgegate.netlify.app)
**API:** [web-production-3941b.up.railway.app/docs](https://web-production-3941b.up.railway.app/docs)

---

## What it does

1. A studio submits a prompt (and optionally a free-text style guide, plus approved exemplar images).
2. Forge Gate generates a candidate image **through Genblaze**, which owns the actual multi-provider orchestration (see below) — not a hand-rolled if/except.
3. An AI critic (Groq vision) checks the candidate against the studio's style guide, with a real, human-readable reason for every pass or fail.
4. A visual similarity check screens for near-duplicates against previously approved exemplars.
5. If a candidate fails, Forge Gate automatically retries with a corrected prompt — up to 3 attempts — before escalating to `needs_human_review`.
6. Every attempt is recorded in a full timeline, **and** chained to its Genblaze run manifest in B2 — the prompt used, the model, the asset, the run's provenance record, and both checks' results and reasoning.

Nothing is a black box. The point isn't "does this look right" — it's "here's exactly why this passed or failed, what happens next, and exactly which run produced it."

## Architecture

```
Frontend (Netlify)
       │
       ▼
FastAPI backend (Railway)
       │
       ├── Generation ── Genblaze Pipeline
       │                   ├── PollinationsProvider (primary — custom SyncProvider adapter)
       │                   └── HuggingFaceProvider (fallback — custom SyncProvider adapter)
       ├── Storage ───── Backblaze B2, via Genblaze's ObjectStorageSink (run-grouped, provenance manifests)
       ├── Style critic ─ Groq vision (llama-4-scout)
       └── Duplicate check ─ perceptual hash + difference hash + color histogram
```

### Real Genblaze orchestration, not a wrapper around one

Generation doesn't call Pollinations or Hugging Face directly. `providers/pollinations.py`
and `providers/huggingface.py` are custom `genblaze_core.providers.SyncProvider`
subclasses that raise typed `ProviderError` codes (`MODEL_ERROR`, `TIMEOUT`,
`RATE_LIMIT`, `AUTH_FAILURE`, ...) on failure. `files/pipeline.py` runs the
primary provider inside a `Pipeline(...).step(...)`, and **Genblaze's own
fallback handling** — not a hand-rolled try/except around two functions — is
what hops to a genuinely different provider/service when the primary is
exhausted. This is tested and proven, not theoretical: kill the primary
provider and watch the second one pick up the job in the same run.

Retries within a single job are chained via Genblaze's result-passing
(`Pipeline.from_result(previous_result)`), so each attempt's run carries a
`parent_run_id` back to the one before it.

### Provenance, not just storage

Every `Attempt` row stores `genblaze_run_id`, `genblaze_parent_run_id`, and
`manifest_b2_url` — Genblaze's own SHA-256-verified provenance manifest for
that exact run, alongside the asset itself, in B2. The `/jobs/{id}/timeline`
endpoint is a walk of that chain: which run produced which asset, what it
was checked against, and why it passed or failed — a fully reconstructable
audit trail, not a bespoke versioning system bolted on afterward.

## Why these choices

Every piece of this stack was deliberately chosen to be free-tier and
keyless where possible, so the whole thing runs without a credit card:

- **Pollinations** — keyless HTTP image generation, no signup.
- **Hugging Face Inference Providers** — free-tier fallback generation, one token.
- **Backblaze B2** — free-tier private object storage, used as Genblaze's storage sink.
- **Groq** — free-tier vision-language model for the style critic, no billing required.
- **Visual similarity via perceptual hashing**, not a CLIP embedding model. This is a deliberate tradeoff: it catches near-duplicates and reused/recolored assets, but not semantic duplicates (e.g. the same character in a different pose). A full CLIP-based approach is the natural upgrade path, but the memory footprint of `torch` doesn't fit on free-tier hosting — this keeps the entire deployed system free to run, indefinitely, with no paid infrastructure anywhere in the stack.

## Tech stack

- **Backend:** FastAPI, SQLAlchemy (SQLite by default, swaps to Postgres via `DATABASE_URL` — see below)
- **Generation:** Genblaze Pipeline, orchestrating custom provider adapters over Pollinations.ai and Hugging Face Inference Providers
- **Storage:** Backblaze B2 (S3-compatible), via `genblaze-core` / `genblaze-s3`'s `ObjectStorageSink`
- **AI critic:** Groq (`meta-llama/llama-4-scout-17b-16e-instruct`)
- **Duplicate detection:** `imagehash` (perceptual + difference hash) + color histogram
- **Frontend:** Vanilla HTML/CSS/JS, deployed on Netlify
- **Hosting:** Railway (backend), Netlify (frontend)

## Production readiness

- **Persistent storage:** `files/db.py` reads `DATABASE_URL` from the environment with a SQLite fallback for local dev. In production, attach a Postgres addon on Railway and set `DATABASE_URL` — no code change needed, job history is durable.
- **Auth:** write endpoints (`POST /jobs`, reference uploads) accept an optional shared-secret `X-API-Key` header, enforced only when `API_SHARED_SECRET` is set (see `files/main.py :: require_api_key`) — locked down in production without breaking local dev.
- **Tested multi-provider failover:** the Pollinations → Hugging Face fallback is driven by Genblaze's own error-code-based retry logic, and has been exercised by deliberately failing the primary provider mid-run.
- **Full provenance chain:** every attempt is traceable to its Genblaze run manifest in B2, not just a raw image URL.

## API

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/studios/{studio_id}/references/style-guide` | Set a studio's free-text style guide |
| `POST` | `/studios/{studio_id}/references/exemplars` | Upload an approved exemplar asset |
| `GET`  | `/studios/{studio_id}/references` | List a studio's references |
| `POST` | `/jobs` | Submit a prompt for generation + review |
| `GET`  | `/jobs/{job_id}` | Get a job's current status |
| `GET`  | `/jobs/{job_id}/timeline` | Full attempt-by-attempt history, chained to Genblaze run manifests |

Full interactive docs: [`/docs`](https://web-production-3941b.up.railway.app/docs)

## Running locally

```bash
git clone https://github.com/ishantgupta30/forge-gate.git
cd forge-gate
pip install -r requirements.txt
cp files/.env.example .env   # fill in your own free-tier keys
python -m uvicorn files.main:app --reload
```

Then open `frontend.html` locally, pointed at `http://127.0.0.1:8000`.

> **Never commit or zip your real `.env` file.** It's already excluded via
> `.gitignore`; if you're packaging the repo for submission, build the zip
> explicitly rather than archiving the whole working directory.

## What's next

- Semantic (CLIP-based) duplicate detection, once hosting allows the memory footprint
- A second AI critic pass for finer-grained style rubrics
- A second Genblaze-orchestrated generation provider beyond Pollinations/Hugging Face, for a third fallback tier
