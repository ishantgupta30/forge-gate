"""PollinationsProvider — free, keyless image generation via Pollinations.ai.

No auth required. One HTTP call returns an image directly, so this uses
SyncProvider (no submit/poll/fetch_output split needed).
"""

from __future__ import annotations

from urllib.parse import quote

from genblaze_core.exceptions import ProviderError
from genblaze_core.models.asset import Asset
from genblaze_core.models.enums import ProviderErrorCode
from genblaze_core.models.step import Step
from genblaze_core.providers import SyncProvider
from genblaze_core.providers.base import validate_asset_url

# Pollinations' real, known model slugs (as of today). Anything else
# is treated as a MODEL_ERROR so Genblaze's fallback_models can fire.
KNOWN_MODELS = {"flux", "turbo", "kontext"}


class PollinationsProvider(SyncProvider):
    name = "pollinations"

    def generate(self, step: Step, config=None) -> Step:
        model = step.model or "flux"

        if model not in KNOWN_MODELS:
            raise ProviderError(
                f"Unknown Pollinations model: {model!r}",
                error_code=ProviderErrorCode.MODEL_ERROR,
            )

        image_url = (
            f"https://image.pollinations.ai/prompt/{quote(step.prompt)}"
            f"?model={quote(model)}&nologo=true"
        )
        validate_asset_url(image_url)
        step.assets.append(Asset(url=image_url, media_type="image/jpeg"))
        return step
