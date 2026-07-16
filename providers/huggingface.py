"""HuggingFaceProvider — free-tier text-to-image via HF Inference API.

Uses a different model/service entirely from Pollinations, so this gives
genuine multi-provider diversity (not just two models on the same backend).
Requires only a free 'Read' token, no billing.
"""
from __future__ import annotations

import tempfile
import httpx
from genblaze_core.exceptions import ProviderError
from genblaze_core.models.asset import Asset
from genblaze_core.models.enums import ProviderErrorCode
from genblaze_core.models.step import Step
from genblaze_core.providers import SyncProvider

KNOWN_MODELS = {
    "flux-schnell": "black-forest-labs/FLUX.1-schnell",
    "sd-turbo": "stabilityai/sd-turbo",
}


class HuggingFaceProvider(SyncProvider):
    name = "huggingface"

    def __init__(self, api_key: str, **kwargs):
        super().__init__(**kwargs)
        self._api_key = api_key

    def generate(self, step: Step, config=None) -> Step:
        model_key = step.model or "flux-schnell"

        if model_key not in KNOWN_MODELS:
            raise ProviderError(
                f"Unknown HuggingFace model: {model_key!r}",
                error_code=ProviderErrorCode.MODEL_ERROR,
            )
        hf_model_id = KNOWN_MODELS[model_key]

        url = f"https://router.huggingface.co/hf-inference/models/{hf_model_id}"
        headers = {"Authorization": f"Bearer {self._api_key}"}

        try:
            resp = httpx.post(
                url,
                headers=headers,
                json={"inputs": step.prompt},
                timeout=60,
            )
        except httpx.TimeoutException as e:
            raise ProviderError(
                f"HuggingFace request timed out: {e}",
                error_code=ProviderErrorCode.TIMEOUT,
            ) from e

        if resp.status_code in (401, 403):
            raise ProviderError(
                f"HuggingFace auth failed: {resp.text[:200]}",
                error_code=ProviderErrorCode.AUTH_FAILURE,
            )
        if resp.status_code == 429:
            raise ProviderError(
                "HuggingFace rate limited",
                error_code=ProviderErrorCode.RATE_LIMIT,
            )
        if resp.status_code == 503:
            raise ProviderError(
                f"HuggingFace model loading: {resp.text[:200]}",
                error_code=ProviderErrorCode.SERVER_ERROR,
            )
        if resp.status_code != 200:
            raise ProviderError(
                f"HuggingFace error {resp.status_code}: {resp.text[:200]}",
                error_code=ProviderErrorCode.UNKNOWN,
            )

        content_type = resp.headers.get("content-type", "")
        if "image" not in content_type:
            raise ProviderError(
                f"HuggingFace did not return an image (got {content_type}): {resp.text[:200]}",
                error_code=ProviderErrorCode.UNKNOWN,
            )

        ext = ".png" if "png" in content_type else ".jpg"
        tmp = tempfile.NamedTemporaryFile(suffix=ext, delete=False)
        tmp.write(resp.content)
        tmp.close()

        step.assets.append(Asset(url=f"file://{tmp.name}", media_type=content_type))
        return step
