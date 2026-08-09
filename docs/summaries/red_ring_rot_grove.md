# Summary: Douglas-fir grove red ring rot prototype

## What changed
- Added a Douglas-fir-dominated inventory generator for a site-specific grove scenario.
- Added a runnable prototype entry point for the red ring rot case.
- Extended the risk output with component columns so the highest-risk trees can be explained more clearly.
- Added a small verification test to confirm the scenario runs and produces non-zero risk scores.

## Verification
The following verification steps were run successfully:
- `pytest tests/test_red_ring_rot_grove.py` → 1 passed
- `python PathogenPy/run_red_ring_rot_grove.py` → produced output image at `outputs/red_ring_rot_grove.png`

## Notes
This remains a prototype scaffold. The current model is still explainable and simple, but it is not yet calibrated against real outbreak data.
