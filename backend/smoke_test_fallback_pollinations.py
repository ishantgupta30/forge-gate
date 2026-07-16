from genblaze_core import Pipeline, Modality
from providers.pollinations import PollinationsProvider

# Force primary to fail with a bogus model string, confirm fallback fires.
result = (
    Pipeline("smoke-fallback")
    .step(
        PollinationsProvider(),
        model="definitely-not-a-real-model-xyz",
        fallback_models=["flux"],
        prompt="a single red apple on a white background",
        modality=Modality.IMAGE,
    )
    .run(timeout=60, raise_on_failure=True)
)
step = result.run.steps[0]
print("status:", step.status)
print("model actually used:", step.model)
print("error_code:", step.error_code)
print(step.assets[0].url if step.assets else "NO ASSET")
