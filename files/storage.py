"""
Backblaze B2 storage sink.

We let Genblaze use its own default run-grouped layout
(runs/{tenant}/{date}/{run_id}/...) rather than fighting it into a custom
per-file layout — this is faster to build and is still fully real B2 usage.
The 4-class system (references / candidates / approvals / production) lives
in OUR database (see models.py), which stores the resulting B2 URLs.
That's what the submission's "B2 usage" writeup should describe.
"""
import os
import boto3
from genblaze_core import ObjectStorageSink, KeyStrategy
from genblaze_s3 import S3StorageBackend
from dotenv import load_dotenv
load_dotenv()
_sink = None
_b2_client = None


def _get_b2_client():
    """
    Plain boto3 S3-compatible client against the same B2 bucket, for uploads
    that AREN'T Genblaze pipeline outputs (e.g. studio-uploaded style guides
    and exemplar images — Step 1 of the workflow, before any generation
    happens). Genblaze's ObjectStorageSink only wires up pipeline run
    outputs, so reference uploads go through this instead, straight to the
    same bucket under a references/ prefix.
    """
    global _b2_client
    if _b2_client is None:
        region = os.getenv("B2_REGION", "us-west-004")
        _b2_client = boto3.client(
            "s3",
            endpoint_url=f"https://s3.{region}.backblazeb2.com",
            aws_access_key_id=os.environ["B2_KEY_ID"],
            aws_secret_access_key=os.environ["B2_APP_KEY"],
            region_name=region,
        )
    return _b2_client


def upload_reference_asset(studio_id: str, filename: str, content: bytes, content_type: str = "image/png") -> str:
    """Uploads a studio's style-guide/exemplar file to references/{studio_id}/{filename} and
    returns its durable B2 URL."""
    bucket = os.environ["B2_BUCKET"]
    key = f"references/{studio_id}/{filename}"
    client = _get_b2_client()
    client.put_object(Bucket=bucket, Key=key, Body=content, ContentType=content_type)
    region = os.getenv("B2_REGION", "us-west-004")
    return f"https://s3.{region}.backblazeb2.com/{bucket}/{key}"


def get_storage_sink() -> ObjectStorageSink:
    global _sink
    if _sink is None:
        backend = S3StorageBackend.for_backblaze(
            os.environ["B2_BUCKET"],
            key_id=os.environ["B2_KEY_ID"],
            app_key=os.environ["B2_APP_KEY"],
            region=os.getenv("B2_REGION", "us-west-004"),
        )
        _sink = ObjectStorageSink(
            backend,
            key_strategy=KeyStrategy.HIERARCHICAL,  # runs/{date}/{run_id}/... — good for browsing
        )
    return _sink
