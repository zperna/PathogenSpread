# Design note: spatial inputs for pathogen risk

## Approach
The prototype now accepts spatial layers. These layers feed the existing risk engine as normalized suitability surfaces.

## Design choices
- Add a new helper module, `PathogenPy/spatial_inputs.py`, to generate and normalize spatial surfaces.
- Keep the core engine generic. Additional environment layers are allowed beyond the original moisture/temp pair.
- Use pathogen-specific `spatial_weights` to control how land cover, soil, terrain, moisture, and temperature combine. The result is a single environmental suitability score.

## Implementation details
- `spatial_inputs.generate_synthetic_spatial_surfaces(...)` creates placeholder raster surfaces for:
  - `moisture`
  - `temp`
  - `terrain`
  - `land_cover`
  - `soil`
- Categorical rasters are converted into normalized suitability surfaces using manual score maps.
- `spread_engine.compute_risk(...)` now attempts to combine spatial surfaces using `pathogen_config["spatial_weights"]`.
- If no spatial weights are present, the engine still falls back to the original moisture/temp logic.

## Assumptions
- The prototype assumes a common projected coordinate system and uniform grid alignment.
- The current spatial surfaces are synthetic placeholders. Real raster ingestion can be added later.
