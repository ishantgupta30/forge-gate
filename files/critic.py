"""
Feature 2: AI Critic — exactly two checks, both framed as enforcing the
studio's own policy, not subjective "beauty."

1. Style consistency — does the candidate match the uploaded style guide?
2. Duplicate detection — is it a near-copy of an already-approved exemplar?

Keep this file boring and inspectable on purpose: judges should be able to
see exactly why something passed or failed, not trust a black-box score.
"""
import base64
import io
import json
import os
import numpy as np
from groq import Groq
from .embeddings import embed_image_from_url, _load_image

DUPLICATE_THRESHOLD = 0.92
_STYLE_MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"


def _image_to_data_url(candidate_url: str) -> str:
    """Fetch the candidate image (using the same authenticated-B2-aware
    loader as embeddings.py, since assets live in a private bucket) and
    return it as a base64 data URL Groq can read directly — avoids Groq's
    server trying and failing to fetch a private/blocked URL itself."""
    image = _load_image(candidate_url)
    buf = io.BytesIO()
    image.save(buf, format="JPEG")
    b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
    return f"data:image/jpeg;base64,{b64}"


def check_style_consistency(candidate_url: str, style_guide_description: str) -> dict:
    """
    Ask a vision-capable model a structured yes/no question against a
    concrete, stated attribute — not a vague 'does this look right' vibe
    check. Keep the question to 1-2 concrete visual attributes.
    """
    client = Groq(api_key=os.environ["GROQ_API_KEY"])
    data_url = _image_to_data_url(candidate_url)

    prompt = (
        f"Reference style requirement: {style_guide_description}\n"
        "Does the attached image match this style requirement? "
        'Answer strictly as JSON: {"match": true or false, "reason": "<one short sentence>"}'
    )

    response = client.chat.completions.create(
        model=_STYLE_MODEL,
        messages=[{
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": data_url}},
            ],
        }],
        response_format={"type": "json_object"},
    )
    parsed = json.loads(response.choices[0].message.content)
    return {"passed": bool(parsed["match"]), "reason": parsed["reason"]}


def embed_image(image_url: str) -> dict:
    """Local, keyless visual signature (hash + color histogram) — see
    embeddings.py. No API key, no heavy ML model required."""
    return embed_image_from_url(image_url)


def check_duplicate(candidate_url: str, approved_exemplar_embeddings: list[tuple[str, np.ndarray]]) -> dict:
    """
    approved_exemplar_embeddings: list of (asset_id, embedding) for every
    already-approved exemplar for this studio.
    """
    candidate_sig = embed_image(candidate_url)

    best_match_id, best_similarity = None, 0.0
    for asset_id, exemplar_sig in approved_exemplar_embeddings:
        similarity = visual_similarity(candidate_sig, exemplar_sig)
        if similarity > best_similarity:
            best_match_id, best_similarity = asset_id, similarity

    is_duplicate = best_similarity >= DUPLICATE_THRESHOLD
    return {
        "passed": not is_duplicate,
        "similarity": best_similarity,
        "matched_asset_id": best_match_id if is_duplicate else None,
    }
