"""
Visual similarity for duplicate detection — Feature 2b.

Deliberately lightweight: no torch/open_clip, so this runs comfortably on
free-tier hosting (512MB-1GB RAM) instead of needing a paid plan. Uses a
combination of perceptual hash, difference hash, and a coarse color
histogram — good at catching near-duplicates, re-crops, recolors, and
minor edits of the *same* image. This is honestly "visual similarity,"
not semantic understanding — it won't recognize the same character
redrawn in a different pose. A CLIP-based embedding model is the natural
upgrade path if hosting RAM headroom allows for it later.
"""
import io
import os
import numpy as np
import requests
from PIL import Image
import imagehash


def _get_b2_client():
    import boto3

    region = os.getenv("B2_REGION", "us-west-004")
    return boto3.client(
        "s3",
        endpoint_url=f"https://s3.{region}.backblazeb2.com",
        aws_access_key_id=os.environ["B2_KEY_ID"],
        aws_secret_access_key=os.environ["B2_APP_KEY"],
        region_name=region,
    )


def _load_image(image_url_or_path: str) -> Image.Image:
    bucket = os.environ.get("B2_BUCKET", "")
    if bucket and f"backblazeb2.com/{bucket}/" in image_url_or_path:
        key = image_url_or_path.split(f"backblazeb2.com/{bucket}/", 1)[1]
        client = _get_b2_client()
        obj = client.get_object(Bucket=bucket, Key=key)
        content = obj["Body"].read()
        return Image.open(io.BytesIO(content)).convert("RGB")

    if image_url_or_path.startswith("http://") or image_url_or_path.startswith("https://"):
        resp = requests.get(image_url_or_path, timeout=30)
        resp.raise_for_status()
        return Image.open(io.BytesIO(resp.content)).convert("RGB")

    return Image.open(image_url_or_path).convert("RGB")


def _color_histogram(image: Image.Image, bins: int = 8) -> np.ndarray:
    """Coarse RGB histogram, flattened and L2-normalized — cheap, catches
    gross color/composition differences that hashing alone can miss."""
    small = image.resize((64, 64))
    arr = np.asarray(small).reshape(-1, 3)
    hist, _ = np.histogramdd(arr, bins=(bins, bins, bins), range=((0, 256),) * 3)
    hist = hist.flatten().astype(np.float32)
    norm = np.linalg.norm(hist)
    return hist / norm if norm > 0 else hist


def embed_image_from_url(image_url: str) -> dict:
    """Returns a combined visual signature: perceptual hash, difference
    hash, and a color histogram vector. Used as a single unit by
    check_duplicate's similarity function."""
    image = _load_image(image_url)
    return {
        "phash": imagehash.phash(image),
        "dhash": imagehash.dhash(image),
        "hist": _color_histogram(image),
    }


def visual_similarity(sig_a: dict, sig_b: dict) -> float:
    """Combines hash distance and histogram similarity into one score in
    [0, 1], where 1.0 means visually identical."""
    max_hash_bits = len(sig_a["phash"].hash) ** 2  # 8x8 hash -> 64 bits
    phash_sim = 1 - (sig_a["phash"] - sig_b["phash"]) / max_hash_bits
    dhash_sim = 1 - (sig_a["dhash"] - sig_b["dhash"]) / max_hash_bits

    hist_a, hist_b = sig_a["hist"], sig_b["hist"]
    hist_sim = float(np.dot(hist_a, hist_b))  # both L2-normalized -> cosine sim

    # Weighted toward hashing (structure) with histogram as a secondary signal.
    return 0.4 * phash_sim + 0.4 * dhash_sim + 0.2 * hist_sim


def embedding_to_json(sig: dict) -> str:
    import json

    return json.dumps({
        "phash": str(sig["phash"]),
        "dhash": str(sig["dhash"]),
        "hist": sig["hist"].tolist(),
    })


def embedding_from_json(s: str) -> dict:
    import json

    data = json.loads(s)
    return {
        "phash": imagehash.hex_to_hash(data["phash"]),
        "dhash": imagehash.hex_to_hash(data["dhash"]),
        "hist": np.array(data["hist"], dtype=np.float32),
    }
