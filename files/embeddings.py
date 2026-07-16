"""
Image embeddings for duplicate detection — Feature 2b.
Deliberately keyless: this runs an open-source CLIP model locally via
open_clip, so duplicate detection works today with zero API keys and zero
GMI/OpenAI dependency.
Model: ViT-B-32 / openai pretrained weights (~350MB, downloads once, then
cached). CPU inference is fine at hackathon scale.
"""
import io
import os
import functools
import numpy as np
import requests
from PIL import Image

_MODEL_NAME = "ViT-B-32"
_PRETRAINED = "openai"


@functools.lru_cache(maxsize=1)
def _load_model():
    import open_clip
    import torch

    model, _, preprocess = open_clip.create_model_and_transforms(_MODEL_NAME, pretrained=_PRETRAINED)
    model.eval()
    return model, preprocess, torch


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


def embed_image_from_url(image_url: str) -> np.ndarray:
    model, preprocess, torch = _load_model()
    image = _load_image(image_url)
    tensor = preprocess(image).unsqueeze(0)

    with torch.no_grad():
        features = model.encode_image(tensor)
        features = features / features.norm(dim=-1, keepdim=True)

    return features.squeeze(0).numpy()


def embedding_to_json(vec: np.ndarray) -> str:
    import json

    return json.dumps(vec.tolist())


def embedding_from_json(s: str) -> np.ndarray:
    import json

    return np.array(json.loads(s), dtype=np.float32)
