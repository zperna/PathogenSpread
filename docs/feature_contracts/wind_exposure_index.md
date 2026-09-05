# Feature contract: Topographic position index for red ring rot's wind-exposure proxy

## Problem
`red_ring_rot["spatial_weights"]["terrain"] = 0.35` -- the largest single
spatial weight in that config -- is documented as "our current proxy for
wind exposure" (`pathogens.py`), backing a pathogen whose transmission
depends on wind-dispersed spores infecting through wounds (see
`docs/feature_contracts/wind_dispersal_and_soil_reweight.md`). The proxy
itself, `spatial_inputs.score_terrain`, is moderate-slope-favorability
averaged with north-facing-aspect -- a generic terrain score with no
particular claim to represent wind exposure specifically. It was already
flagged as a placeholder in that earlier contract and again as an open
non-goal in `docs/feature_contracts/topographic_wetness_index.md`
("No attempt to improve the wind-exposure proxy itself... out of scope
here, a separate future contract if pursued") when `phytophthora`'s
matching `terrain` weight was replaced with a purpose-built topographic
wetness index instead of the same generic score.

A real directional wind-exposure measure would need prevailing wind
direction/strength data, which doesn't exist for this site (tracked as a
blocked dependency, "Part B", in `wind_dispersal_and_soil_reweight.md`).
But direction isn't the only thing that predicts wind exposure/damage in
forestry: **topographic position** -- whether a cell sits on a ridge/
convex landform (exposed to wind from most directions) versus a valley/
concave landform (sheltered) -- is a well-established, direction-independent
proxy for wind exposure and windthrow risk, and it's derivable from the
DEM already exported for this project, the same way TWI was for wetness.

## Goal
Add a DEM-derived Topographic Position Index (TPI) surface as an
`exposure` measure, and use it as `red_ring_rot`'s terrain-proxy weight
instead of the current generic slope/aspect score -- the same kind of
per-pathogen swap as the phytophthora/wetness change, not a change to
`score_terrain` itself or to any other pathogen's config.

## Scope
- In `export_site_layers.py`'s `export_terrain`, derive TPI from the
  already-exported local DEM clip (`dem.tif`), in the same function as
  slope/aspect/TWI (DEM is already local by that point):
  `TPI = elevation - focal_mean(elevation, neighborhood)`, via
  `arcpy.sa.FocalStatistics`. Export alongside the existing rasters.
- Add a new `exposure` surface to `spatial_inputs.load_site_grid`:
  per-site min-max normalize the raw TPI array -- higher TPI (more
  ridge-like/convex) = more exposed = higher suitability for this
  pathogen, no inversion needed, same pattern as `wetness`.
- Update `red_ring_rot["spatial_weights"]` in `pathogens.py`: replace the
  `terrain` key with `exposure` (same 0.35 weight -- this pass replaces
  the proxy, not the weight, consistent with how the wetness swap handled
  its own weight).
- Re-run the full pipeline (export -> compute -> import) for both sites.
- Apply the float-NoData handling established in the wetness work
  (`nodata_to_value=np.nan`, neutral 0.5 fallback) to the new TPI raster
  from the start -- this is now a known failure mode for any DEM-derived
  float surface (see [[feedback-arcpy-float-nodata-sentinel]]), not
  something to rediscover.

## Non-goals
- `phytophthora` is untouched -- already uses `wetness`, not `terrain`.
- `terrain`/`score_terrain` itself is not removed or changed -- kept
  available in `spatial_inputs.py` in case a future pathogen config wants
  a generic slope/aspect surface. After this change it has no current
  consumer in `pathogens.py`, which is fine; it's infrastructure, not
  dead code slated for deletion.
- No directional wind kernel -- still blocked on real wind data, per
  `wind_dispersal_and_soil_reweight.md` Part B. TPI is a direction-
  independent complement to that future work, not a substitute for it.
- No re-tuning of the 0.35 weight itself, or of any other
  `red_ring_rot` parameter.
- Doesn't address `anthracnose`/`emerald_ash_borer`'s missing
  `spatial_weights` blocks -- a separate, already-identified gap, not
  pursued here.
- No claim that TPI-based exposure is a *validated* wind-exposure measure
  for this specific site or pathogen -- a standard, literature-grounded
  terrain metric standing in for a real driver, same caveat as every
  other suitability surface in this project.

## Inputs
- `data/<site>/gis_reference/dem.tif` (already exported) -- no new
  external data source.

## Outputs
- `data/<site>/gis_reference/exposure_index.tif` (raw TPI, continuous).
- `data/<site>/exposure_index.npy`.
- `load_site_grid`'s returned environment dict gains an `exposure` key
  (0-1 normalized) alongside the existing `terrain`.
- `red_ring_rot["spatial_weights"]` now references `exposure` instead of
  `terrain`; `phytophthora` unchanged.
- Updated `outputs/red_ring_rot_site_risk.npy`/`.tif`/preview.
  `phytophthora`'s output should be numerically unchanged (regression
  check, mirroring how `red_ring_rot`'s output was checked byte-identical
  during the wetness-index work).

## Success criteria
- Both sites' exports run end to end, no `ValueError`/shape mismatch, and
  no float-NoData contamination in the new raster (checked directly via
  `np.isnan`/percentile stats before trusting the normalized surface --
  the wetness-index work showed this can silently produce a
  plausible-looking but wrong result otherwise).
- The new `exposure` surface is visibly different from the existing
  `terrain` surface in each AOI (checked directly, not just eyeballed in
  the final raster).
- `phytophthora`'s risk raster output is numerically identical (ideally
  byte-identical, per `git status`) before/after this change.
- `run_real_site_risk_raster.py` and `import_risk_raster.py` still run
  cleanly for both pathogens.

## Definition of done
- This contract exists (done).
- Design note, implementation, verification, and update summary follow in
  `docs/notes/wind_exposure_index.md`.
