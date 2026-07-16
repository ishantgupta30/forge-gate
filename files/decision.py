"""
Feature 3: Decision Engine — the actual product.

generate -> critic checks -> pass? approve : retry with a specific,
inspectable prompt correction -> after MAX_RETRY_ATTEMPTS, escalate to
Needs Human Review.

The prompt correction is deliberately rule-based and small, NOT a magic
black-box rewrite — show the before/after diff on screen during the demo.
"""
import os
from sqlalchemy.orm import Session
from .models import Job, Attempt
from .pipeline import generate_candidate
from .critic import check_style_consistency, check_duplicate, embed_image

MAX_RETRY_ATTEMPTS = int(os.getenv("MAX_RETRY_ATTEMPTS", 3))

# Small, fixed, inspectable correction lists — NOT free-form "AI rewrites this."
STYLE_FIX_SUFFIX = ", matching the studio's approved style guide exactly"
DUPLICATE_FIX_OPTIONS = [
    ", different pose",
    ", different hair color",
    ", different background lighting",
]


def _next_prompt(base_prompt: str, style_failed: bool, duplicate_failed: bool, attempt_number: int) -> str:
    prompt = base_prompt
    if style_failed:
        prompt += STYLE_FIX_SUFFIX
    if duplicate_failed:
        prompt += DUPLICATE_FIX_OPTIONS[(attempt_number - 1) % len(DUPLICATE_FIX_OPTIONS)]
    return prompt


def run_job(db: Session, job: Job, style_guide_description: str, approved_exemplar_embeddings: list):
    prompt = job.original_prompt
    previous_genblaze_result = None

    for attempt_number in range(1, MAX_RETRY_ATTEMPTS + 1):
        gen = generate_candidate(prompt, previous_result=previous_genblaze_result)
        previous_genblaze_result = gen["result"]

        style_result = check_style_consistency(gen["asset_url"], style_guide_description)
        dup_result = check_duplicate(gen["asset_url"], approved_exemplar_embeddings)

        attempt = Attempt(
            job_id=job.id,
            attempt_number=attempt_number,
            prompt_used=prompt,
            provider="pollinations",
            model=gen["provider_model_used"],
            genblaze_run_id=gen["run_id"],
            genblaze_parent_run_id=gen["parent_run_id"],
            asset_b2_url=gen["asset_url"],
            manifest_b2_url=gen["manifest_url"],
            asset_sha256=gen["asset_sha256"],
            style_check_passed=style_result["passed"],
            style_check_reason=style_result["reason"],
            duplicate_check_passed=dup_result["passed"],
            duplicate_check_similarity=dup_result["similarity"],
            duplicate_check_matched_asset_id=dup_result["matched_asset_id"],
        )

        if style_result["passed"] and dup_result["passed"]:
            attempt.final_status = "approved"
            db.add(attempt)
            job.status = "approved"
            job.final_attempt_id = attempt.id
            db.commit()
            return {"status": "approved", "attempt": attempt}

        attempt.final_status = "rejected"
        db.add(attempt)
        db.commit()

        if attempt_number == MAX_RETRY_ATTEMPTS:
            job.status = "needs_human_review"
            db.commit()
            return {"status": "needs_human_review", "attempt": attempt}

        prompt = _next_prompt(
            job.original_prompt,
            style_failed=not style_result["passed"],
            duplicate_failed=not dup_result["passed"],
            attempt_number=attempt_number,
        )

    # unreachable, but keeps type checkers happy
    return {"status": "needs_human_review", "attempt": None}
