import os
from genblaze_core import Pipeline, Modality
from genblaze_core.exceptions import PipelineError
from providers.pollinations import PollinationsProvider
from providers.huggingface import HuggingFaceProvider
from .storage import get_storage_sink

PRIMARY_MODEL = "flux"
FALLBACK_MODELS = ["turbo"]


def _run_pollinations(prompt: str, sink, previous_result=None):
    builder = Pipeline("forge-gate-generation")
    if previous_result is not None:
        builder = builder.from_result(previous_result)

    return (
        builder.step(
            PollinationsProvider(),
            model=PRIMARY_MODEL,
            fallback_models=FALLBACK_MODELS,
            prompt=prompt,
            modality=Modality.IMAGE,
        ).run(sink=sink, timeout=180, raise_on_failure=True)
    )


def _run_huggingface(prompt: str, sink, previous_result=None):
    builder = Pipeline("forge-gate-generation-hf")
    if previous_result is not None:
        builder = builder.from_result(previous_result)

    return (
        builder.step(
            HuggingFaceProvider(api_key=os.environ["HF_TOKEN"]),
            model="flux-schnell",
            fallback_models=["sd-turbo"],
            prompt=prompt,
            modality=Modality.IMAGE,
        ).run(sink=sink, timeout=180, raise_on_failure=True)
    )


def generate_candidate(prompt: str, previous_result=None):
    sink = get_storage_sink()

    try:
        result = _run_pollinations(prompt, sink, previous_result)
    except PipelineError as e:
        # Real cross-provider fallback: Pollinations (and its own
        # same-provider fallback_models) exhausted, so hop to a genuinely
        # different provider/service entirely rather than failing the job.
        print(f"[fallback] Pollinations failed ({e}); retrying on HuggingFace")
        result = _run_huggingface(prompt, sink, previous_result)

    step = result.run.steps[0]
    asset = step.assets[0]
    return {
        "result": result,
        "run_id": result.run.run_id,
        "parent_run_id": result.run.parent_run_id,
        "provider_model_used": step.model,
        "asset_url": asset.url,
        "asset_sha256": asset.sha256,
        "manifest_url": result.manifest.manifest_uri,
    }
