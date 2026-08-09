# Summary: spatial inputs feature

## What changed
- Added `PathogenPy/spatial_inputs.py` to generate and normalize raster-derived suitability surfaces.
- Extended the risk engine to combine multiple spatial layers using pathogen-specific weights.
- Updated the Douglas-fir red ring rot prototype runner to use the new spatial surfaces.

## Verification
- Added `tests/test_spatial_inputs.py`.
- `pytest tests/test_spatial_inputs.py tests/test_red_ring_rot_grove.py` → `3 passed`
- `python PathogenPy/run_red_ring_rot_grove.py` → produced `outputs/red_ring_rot_grove.png`

## Notes
This feature is a prototype bridge from real spatial data into the existing engine. The next step is to replace synthetic surfaces with actual land cover, soil, and terrain rasters from the study site.
