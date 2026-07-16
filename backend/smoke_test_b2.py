from genblaze_core import Pipeline, Modality
from providers.pollinations import PollinationsProvider
from storage import build_b2_sink

sink = build_b2_sink()

result = (
    Pipeline("smoke-b2")
    .step(
        PollinationsProvider(),
        model="flux",
        prompt="a single red apple on a white background",
        modality=Modality.IMAGE,
    )
    .run(timeout=60, raise_on_failure=True, sink=sink)
)

step = result.run.steps[0]
print("status:", step.status)
print("asset url (should be a B2/S3 URL now, not pollinations.ai):")
print(step.assets[0].url if step.assets else "NO ASSET")
