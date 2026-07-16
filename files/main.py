import json
from fastapi import FastAPI, Depends, UploadFile, File, Form, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel

from .db import Base, engine, get_db
from .models import Job, Attempt, ReferenceAsset
from .decision import run_job
from .storage import upload_reference_asset
from .embeddings import embed_image_from_url, embedding_to_json, embedding_from_json
from dotenv import load_dotenv
load_dotenv()

from dotenv import load_dotenv
load_dotenv()

import json
from fastapi import FastAPI, Depends, UploadFile, File, Form, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Forge Gate")


@app.on_event("startup")
def _preload_clip_model():
    """Load the CLIP model once at container startup instead of on the
    first request — avoids a slow first request that can exceed the
    platform's reverse-proxy timeout."""
    from .embeddings import _load_model
    _load_model()

from fastapi.middleware.cors import CORSMiddleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class CreateJobRequest(BaseModel):
    studio_id: str
    prompt: str


def _load_studio_references(db: Session, studio_id: str):
    """Step 1 of the workflow: pull this studio's uploaded style guide + every
    approved exemplar's cached embedding, so a job is judged against what the
    studio actually uploaded — not a placeholder string."""
    rows = db.query(ReferenceAsset).filter(ReferenceAsset.studio_id == studio_id).all()

    style_guide_description = "matches the studio's uploaded reference style"
    exemplar_embeddings: list = []

    for row in rows:
        if row.label == "style_guide":
            # style_guide.json holds the free-text description; b2_url points at it
            style_guide_description = row.embedding_json or style_guide_description
        else:
            if row.embedding_json:
                exemplar_embeddings.append((row.id, embedding_from_json(row.embedding_json)))

    return style_guide_description, exemplar_embeddings


@app.post("/studios/{studio_id}/references/style-guide")
def upload_style_guide(studio_id: str, description: str = Form(...), db: Session = Depends(get_db)):
    """Free-text style guide, e.g. 'cel-shaded, muted earth tones, rounded
    silhouettes, no visible outlines thicker than 2px.' Stored directly
    (no image), keyed off label='style_guide' so it's easy to find later."""
    existing = (
        db.query(ReferenceAsset)
        .filter(ReferenceAsset.studio_id == studio_id, ReferenceAsset.label == "style_guide")
        .first()
    )
    if existing:
        existing.embedding_json = description  # reused as free-text storage for this row type
        db.commit()
        return {"id": existing.id, "updated": True}

    row = ReferenceAsset(studio_id=studio_id, label="style_guide", b2_url="", embedding_json=description)
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"id": row.id, "updated": False}


@app.post("/studios/{studio_id}/references/exemplars")
async def upload_exemplar(
    studio_id: str,
    label: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """Studio uploads an already-approved asset to guard against future
    near-duplicates. We upload it to B2, embed it once here (not on every
    future job), and cache the vector — duplicate checks then just compare
    against cached vectors instead of re-embedding every exemplar per job."""
    content = await file.read()
    b2_url = upload_reference_asset(studio_id, f"{label}_{file.filename}", content, file.content_type or "image/png")

    vec = embed_image_from_url(b2_url)

    row = ReferenceAsset(
        studio_id=studio_id,
        label=label,
        b2_url=b2_url,
        embedding_json=embedding_to_json(vec),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"id": row.id, "b2_url": b2_url}


@app.get("/studios/{studio_id}/references")
def list_references(studio_id: str, db: Session = Depends(get_db)):
    rows = db.query(ReferenceAsset).filter(ReferenceAsset.studio_id == studio_id).all()
    return [{"id": r.id, "label": r.label, "b2_url": r.b2_url} for r in rows]


@app.post("/jobs")
def create_job(req: CreateJobRequest, db: Session = Depends(get_db)):
    job = Job(studio_id=req.studio_id, original_prompt=req.prompt)
    db.add(job)
    db.commit()
    db.refresh(job)

    style_guide_description, approved_exemplar_embeddings = _load_studio_references(db, req.studio_id)
    if not approved_exemplar_embeddings:
        # Not fatal — duplicate check will just always pass with no exemplars
        # to compare against — but worth a heads up during dev/demo prep.
        pass

    result = run_job(db, job, style_guide_description, approved_exemplar_embeddings)
    return {"job_id": job.id, "status": result["status"]}


@app.get("/asset-proxy")
def asset_proxy(url: str):
    """Streams a private B2 asset back to the browser using our own
    authenticated credentials, so <img> tags can render assets from a
    private bucket without making the bucket public."""
    import os
    import boto3
    from fastapi.responses import Response

    bucket = os.environ["B2_BUCKET"]
    if f"backblazeb2.com/{bucket}/" not in url:
        raise HTTPException(status_code=400, detail="URL not in configured bucket")
    key = url.split(f"backblazeb2.com/{bucket}/", 1)[1]

    region = os.getenv("B2_REGION", "us-west-004")
    client = boto3.client(
        "s3",
        endpoint_url=f"https://s3.{region}.backblazeb2.com",
        aws_access_key_id=os.environ["B2_KEY_ID"],
        aws_secret_access_key=os.environ["B2_APP_KEY"],
        region_name=region,
    )
    obj = client.get_object(Bucket=bucket, Key=key)
    return Response(content=obj["Body"].read(), media_type=obj.get("ContentType", "image/jpeg"))


@app.get("/jobs/{job_id}")
def get_job(job_id: str, db: Session = Depends(get_db)):
    job = db.query(Job).filter(Job.id == job_id).first()
    return {
        "id": job.id,
        "status": job.status,
        "original_prompt": job.original_prompt,
        "attempt_count": len(job.attempts),
    }


@app.get("/jobs/{job_id}/timeline")
def get_timeline(job_id: str, db: Session = Depends(get_db)):
    """Feature 4: walk the attempts for this job — this is what the
    Timeline UI renders directly."""
    attempts = (
        db.query(Attempt)
        .filter(Attempt.job_id == job_id)
        .order_by(Attempt.attempt_number)
        .all()
    )
    return [
        {
            "attempt_number": a.attempt_number,
            "prompt_used": a.prompt_used,
            "model": a.model,
            "asset_url": a.asset_b2_url,
            "manifest_url": a.manifest_b2_url,
            "style_check_passed": a.style_check_passed,
            "style_check_reason": a.style_check_reason,
            "duplicate_check_passed": a.duplicate_check_passed,
            "duplicate_check_similarity": a.duplicate_check_similarity,
            "final_status": a.final_status,
        }
        for a in attempts
    ]
