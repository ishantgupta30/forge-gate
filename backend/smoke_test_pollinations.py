from genblaze_core import Pipeline, Modality
from providers.pollinations import PollinationsProvider

result = (
    Pipeline("smoke-pollinations")
    .step(
        PollinationsProvider(),
        model="flux",
        prompt="a single red apple on a white background",
        modality=Modality.IMAGE,
    )
    .run(timeout=60, raise_on_failure=True)
)
print(result.run.steps[0].status, result.run.steps[0].error_code)
print(result.run.steps[0].assets[0].url if result.run.steps[0].assets else "NO ASSET")
