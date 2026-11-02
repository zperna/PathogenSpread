# Feature contract: Topographic wetness index for phytophthora's terrain proxy

## Problem
`spatial_inputs.score_terrain(slope_degrees, aspect_degrees)` is the only terrain surface today. It serves two different physical claims, depending on the pathogen:

- `phytophthora["spatial_weights"]["terrain"] = 0.25`. `pathogens.py` documents this as "a proxy for where water pools" (root-rot pathogen, `moisture_weight: 0.9`).
- `red_ring_rot["spatial_weights"]["terrain"] = 0.35`. Documented as "our current proxy for wind exposure" (airborne, wound-infecting pathogen).

Both pathogens currently get the same score. Moderate slope (peak at 15 degrees) is averaged with north-facing aspect. That is a defensible enough proxy for wind exposure, meaning sheltered or exposed slope orientation. It is not a wetness measure.

Slope and aspect alone say nothing about whether water from upslope collects at a given cell. Consider two cells. One sits partway down a long slope, below a large contributing basin. The other sits on an isolated knob with the same slope and aspect. Today both get the same score. Their real wetness differs a lot.

A Topographic Wetness Index (TWI) is the standard terrain-derived proxy for this. It is `ln(contributing_area / tan(slope))`. It measures how much water a cell tends to collect from upslope. It does not depend only on local slope and aspect. TWI fits phytophthora's documented "where water pools" claim better than the current score. `docs/feature_contracts/soil_water_attributes.md`'s non-goals flagged this as a follow-up.

## Goal
Add a DEM-derived TWI surface. Use it as phytophthora's terrain-proxy weight in place of the current slope and aspect score. Do not change `red_ring_rot`'s existing terrain surface. Wind exposure and water accumulation are different physical quantities. TWI is not a better proxy for wind exposure.

This is a per-pathogen swap. It is not a replacement of `score_terrain` itself.

## Scope
- In `export_site_layers.py`'s `export_terrain`, derive TWI from the already-exported local DEM clip (`dem.tif`). Use the standard Fill, FlowDirection, FlowAccumulation, and TWI chain (`arcpy.sa`).
- Export TWI alongside the existing slope and aspect rasters, in the same pass. The DEM is already local at that point. No new data source is needed.
- Add a new `wetness` surface (a distinct key from `terrain`) to `spatial_inputs.load_site_grid`. Min-max normalize the raw TWI array per site to 0-1. This uses the same pattern as `water_table_depth_in`. Higher TWI means more accumulation and higher suitability. No inversion is needed.
- Update `phytophthora["spatial_weights"]` in `pathogens.py`. Replace the `terrain` key with `wetness`, at the same 0.25 weight. The weight changes only if the diagnostic comparison in verification gives a reason to revisit the number. Changing the number is not the intent of this pass.
- Re-run the full pipeline (export, compute, import) for both sites.

## Non-goals
- `red_ring_rot["spatial_weights"]["terrain"]` is not changed. It stays the existing slope and aspect wind-exposure proxy. TWI is not a substitute for a wind-exposure measure.
- No attempt is made to improve the wind-exposure proxy itself, for example with a real exposure or openness index. That is out of scope here. It would need a separate future contract.
- No claim is made that TWI-based wetness is a *validated* driver of phytophthora spread. This carries the same caveat as every other suitability surface in this project. It is a standard, explainable terrain metric that stands in for a real driver. It is not a calibrated model.
- Edge effects: TWI's contributing-area term is computed only within each site's 2 km AOI clip. Cells near the AOI boundary therefore undercount upslope contributing area from outside the clip. Their true wetness may be higher than the computed value. This is not corrected in this pass. It is a known limitation. AOI-edge effects are handled and disclosed the same way elsewhere, for example by the pixel-alignment crop in `export_case_layer`.
- This does not touch `anthracnose` or `emerald_ash_borer`. Neither has a `spatial_weights` block that uses `terrain`.

## Inputs
- `data/<site>/gis_reference/dem.tif`. The existing `export_terrain` already exports this, as a local copy of the ODF DEM clip. No new external data source is needed.

## Outputs
- `data/<site>/gis_reference/wetness_index.tif` (raw TWI, continuous).
- `data/<site>/wetness_index.npy`.
- The environment dict returned by `spatial_inputs.load_site_grid` gains a `wetness` key (0-1 normalized). It sits alongside the existing `terrain` key.
- `phytophthora["spatial_weights"]` now references `wetness` instead of `terrain`. `red_ring_rot` is unchanged.
- Updated `outputs/phytophthora_site_risk.npy`, `.tif`, and preview. The `red_ring_rot` output should not change numerically, since its config and inputs are not touched. That makes it a useful regression check.

## Success criteria
- Both sites' exports run end to end, with no `ValueError` and no shape mismatch.
- The new `wetness` surface is visibly different from the existing `terrain` surface in each AOI. Check this directly, not by eyeballing the final raster. If it is not different, TWI adds nothing that the slope and aspect proxy did not already capture.
- `red_ring_rot`'s risk raster output is numerically identical before and after this change. This is a regression check. It confirms the phytophthora-only swap did not leak into the other pathogen's config or code path.
- `run_real_site_risk_raster.py` and `import_risk_raster.py` still run cleanly for both pathogens.

## Definition of done
- This contract exists (done).
- The design note, implementation, verification, and update summary follow in `docs/notes/topographic_wetness_index.md`.
