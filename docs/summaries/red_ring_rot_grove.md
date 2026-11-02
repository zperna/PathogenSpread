# Summary: Douglas-fir grove red ring rot prototype

## What changed
- Added a Douglas-fir-dominated inventory generator for a site-specific grove scenario.
- Added a runnable prototype entry point for the red ring rot case.
- Extended the risk output with component columns. The highest-risk trees are easier to explain.
- Added a small verification test. It confirms the scenario runs and produces non-zero risk scores.

## Verification
The following verification steps ran successfully:
1. `pytest tests/test_red_ring_rot_grove.py` → 1 passed
2. `python PathogenPy/run_red_ring_rot_grove.py` → produced output image at `outputs/red_ring_rot_grove.png`

## Notes
This remains a prototype scaffold. The model is still explainable and simple. It is not yet calibrated against real outbreak data.
