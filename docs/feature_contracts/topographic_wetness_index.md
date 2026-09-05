# Feature contract: Topographic wetness index for phytophthora's terrain proxy

## Problem
`spatial_inputs.score_terrain(slope_degrees, aspect_degrees)` is the only
terrain surface today, and it's used for two different physical claims
depending on the pathogen:

- `phytophthora["spatial_weights"]["terrain"] = 0.25` -- documented in
  `pathogens.py` as "a proxy for where water pools" (root-rot pathogen,
  `moisture_weight: 0.9`).
- `red_ring_rot["spatial_weights"]["terrain"] = 0.35` -- documented as "our
  current proxy for wind exposure" (airborne, wound-infecting pathogen).

Both pathogens currently get the *same* score: moderate slope (peak at 15
degrees) averaged with north-facing aspect. That's a defensible-enough
proxy for wind exposure (sheltered vs. exposed slope orientation), but it
is not a wetness measure -- slope and aspect alone say nothing about
whether water draining off upslope terrain actually accumulates at a given
cell. A cell partway down a long slope below a large contributing basin and
a cell of identical slope/aspect on an isolated knob get the same score
today, despite very different real wetness.

A Topographic Wetness Index (TWI) -- `ln(contributing_area / tan(slope))`
-- is the standard terrain-derived proxy for exactly this: how much a cell
tends to accumulate water from upslope, not just its own local slope/
aspect. It's a better fit for phytophthora's documented "where water pools"
claim than the current slope/aspect score. Flagged as a follow-up in
`docs/feature_contracts/soil_water_attributes.md`'s non-goals.

## Goal
Add a DEM-derived TWI surface and use it as phytophthora's terrain-proxy
weight instead of the current slope/aspect score, without disturbing
`red_ring_rot`'s existing terrain surface -- wind exposure and water
accumulation are different physical quantities, and TWI is not a better
proxy for the former. This is a per-pathogen swap, not a replacement of
`score_terrain` itself.

## Scope
- In `export_site_layers.py`'s `export_terrain`, derive TWI from the
  already-exported local DEM clip (`dem.tif`) via the standard
  Fill -> FlowDirection -> FlowAccumulation -> TWI chain (`arcpy.sa`).
  Export alongside the existing slope/aspect rasters, in the same pass
  (DEM is already local at that point, no new data source).
- Add a new `wetness` surface (distinct key from `terrain`) to
  `spatial_inputs.load_site_grid`: per-site min-max normalize the raw TWI
  array to 0-1 (same pattern as `water_table_depth_in` -- higher TWI =
  more accumulation = higher suitability, no inversion needed).
- Update `phytophthora["spatial_weights"]` in `pathogens.py`: replace the
  `terrain` key with `wetness` (same 0.25 weight, unless the diagnostic
  comparison in verification gives reason to revisit the number itself --
  not the intent of this pass).
- Re-run the full pipeline (export -> compute -> import) for both sites.

## Non-goals
- `red_ring_rot["spatial_weights"]["terrain"]` is untouched -- stays the
  existing slope/aspect wind-exposure proxy. TWI is not a substitute for a
  wind-exposure measure.
- No attempt to improve the wind-exposure proxy itself (e.g. a real
  exposure/openness index) -- out of scope here, a separate future
  contract if pursued.
- No claim that TWI-based wetness is a *validated* driver of phytophthora
  spread -- same caveat as every other suitability surface in this
  project: a standard, explainable terrain metric standing in for a real
  driver, not a calibrated model.
- Edge effects: TWI's contributing-area term is computed only within each
  site's 2 km AOI clip, so cells near the AOI boundary systematically
  under-count upslope contributing area from outside the clip (their true
  wetness may be higher than computed). Not corrected in this pass --
  documented as a known limitation, consistent with how AOI-edge effects
  are already handled/disclosed elsewhere (e.g. the pixel-alignment crop
  in `export_case_layer`).
- Doesn't touch `anthracnose` or `emerald_ash_borer` -- neither currently
  has a `spatial_weights` block using `terrain`.

## Inputs
- `data/<site>/gis_reference/dem.tif` (already exported by the existing
  `export_terrain`, local copy of the ODF DEM clip) -- no new external data
  source.

## Outputs
- `data/<site>/gis_reference/wetness_index.tif` (raw TWI, continuous).
- `data/<site>/wetness_index.npy`.
- `spatial_inputs.load_site_grid`'s returned environment dict gains a
  `wetness` key (0-1 normalized) alongside the existing `terrain`.
- `phytophthora["spatial_weights"]` now references `wetness` instead of
  `terrain`; `red_ring_rot` unchanged.
- Updated `outputs/phytophthora_site_risk.npy`/`.tif`/preview (red ring
  rot's output should be numerically unchanged, since its config and
  inputs aren't touched -- a useful regression check).

## Success criteria
- Both sites' exports run end to end with no `ValueError`/shape mismatch.
- The new `wetness` surface is visibly different from the existing
  `terrain` surface in each AOI (checked directly, not just eyeballed in
  the final raster) -- otherwise TWI isn't adding anything the slope/
  aspect proxy didn't already capture.
- `red_ring_rot`'s risk raster output is numerically identical before/after
  this change (regression check that the phytophthora-only swap didn't
  leak into the other pathogen's config or code path).
- `run_real_site_risk_raster.py` and `import_risk_raster.py` still run
  cleanly for both pathogens.

## Definition of done
- This contract exists (done).
- Design note, implementation, verification, and update summary follow in
  `docs/notes/topographic_wetness_index.md`.
