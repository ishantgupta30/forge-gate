"""B2 storage sink wiring — builds an ObjectStorageSink backed by Backblaze B2."""

from __future__ import annotations

import os

from dotenv import load_dotenv
from genblaze_core import KeyStrategy
from genblaze_core.storage.sink import ObjectStorageSink
from genblaze_s3 import S3StorageBackend

load_dotenv()


def build_b2_sink() -> ObjectStorageSink:
    bucket = os.environ["B2_BUCKET"]
    key_id = os.environ["B2_KEY_ID"]
    app_key = os.environ["B2_APP_KEY"]
    region = os.environ["B2_REGION"]

    backend = S3StorageBackend.for_backblaze(
        bucket,
        region=region,
        key_id=key_id,
        app_key=app_key,
    )

    return ObjectStorageSink(
        backend,
        key_strategy=KeyStrategy.HIERARCHICAL,
    )
