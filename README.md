# Forge Gate

**The approval pipeline for AI-generated game assets.**

Forge Gate generates game assets from a text prompt, checks each candidate against a studio's own style guide and prior approved work using a real AI critic, and automatically retries or escalates to human review — so nothing gets approved without a reason attached to it.

**Live demo:** [forgegate.netlify.app](https://forgegate.netlify.app)
**API:** [web-production-3941b.up.railway.app/docs](https://web-production-3941b.up.railway.app/docs)

---

## What it does

1. A studio submits a prompt (and optionally a free-text style guide).
2. Forge Gate generates a candidate image.
3. An AI critic checks the candidate against the studio's style guide, with a real, human-readable reason for every pass or fail.
4. A visual similarity check screens for near-duplicates against previously approved exemplars.
5. If a candidate fails, Forge Gate automatically retries with a corrected prompt — up to 3 attempts — before escalating to `needs_human_review`.
6. Every attempt is recorded in a full timeline: the prompt used, the model, the asset, and both checks' results and reasoning.

Nothing is a black box. The point isn't "does this look right" — it's "here's exactly why this passed or failed, and what happens next."

## Architecture        
Frontend (Netlify)
│
▼
FastAPI backend (Railway)
│
├── Generation ── Pollinations (primary) → Hugging Face (fallback)
├── Storage ───── Backblaze B2 (private bucket, authenticated)
├── Style critic ─ Groq vision (llama-4-scout)
└── Duplicate check ─ perceptual hash + color histogram                                                                                                                                                                     **Real multi-provider fallback.** If the primary image generator fails, Forge Gate automatically retries on a completely different provider — not just a different model on the same service. This is tested and proven, not theoretical: kill the primary provider and watch the second one pick up the job in the same run.

## Why these choices

Every piece of this stack was deliberately chosen to be free-tier and keyless where possible, so the whole thing runs without a credit card:

- **Pollinations** — keyless HTTP image generation, no signup.
- **Hugging Face Inference Providers** — free-tier fallback generation, one token.
- **Backblaze B2** — free-tier private object storage.
- **Groq** — free-tier vision-language model for the style critic, no billing required.
- **Visual similarity via perceptual hashing**, not a CLIP embedding model. This is a deliberate tradeoff: it catches near-duplicates and reused/recolored assets, but not semantic duplicates (e.g. the same character in a different pose). A full CLIP-based approach is the natural upgrade path, but the memory footprint of `torch` doesn't fit on free-tier hosting — this keeps the entire deployed system free to run, indefinitely, with no paid infrastructure anywhere in the stack.

## Tech stack

- **Backend:** FastAPI, SQLAlchemy, SQLite
- **Generation:** Pollinations.ai, Hugging Face Inference Providers
- **Storage:** Backblaze B2 (S3-compatible), via `genblaze-core` / `genblaze-s3`
- **AI critic:** Groq (`meta-llama/llama-4-scout-17b-16e-instruct`)
- **Duplicate detection:** `imagehash` (perceptual + difference hash) + color histogram
- **Frontend:** Vanilla HTML/CSS/JS, deployed on Netlify
- **Hosting:** Railway (backend), Netlify (frontend)

## API

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/studios/{studio_id}/references/style-guide` | Set a studio's free-text style guide |
| `POST` | `/studios/{studio_id}/references/exemplars` | Upload an approved exemplar asset |
| `GET`  | `/studios/{studio_id}/references` | List a studio's references |
| `POST` | `/jobs` | Submit a prompt for generation + review |
| `GET`  | `/jobs/{job_id}` | Get a job's current status |
| `GET`  | `/jobs/{job_id}/timeline` | Full attempt-by-attempt history |

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

## What's next

- Semantic (CLIP-based) duplicate detection, once hosting allows the memory footprint
- A second AI critic pass for finer-grained style rubrics
- Persistent (non-ephemeral) job history in production
