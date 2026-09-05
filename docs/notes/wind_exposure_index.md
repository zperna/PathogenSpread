# Design note: Topographic position index (wind exposure)

## Approach
`export_terrain` gains a fourth derived raster alongside slope/aspect/TWI,
computed from the same local DEM clip (`dem.tif`):

1. `arcpy.sa.FocalStatistics(dem_local, neighborhood, "MEAN")` -- mean
   elevation within a circular neighborhood around each cell.
   `arcpy.sa.NbrCircle(EXPOSURE_RADIUS_CELLS, "CELL")` defines the
   neighborhood; radius in cells, not map units, so it scales correctly
   with `CELL_SIZE_M`.
2. `TPI = dem_local - focal_mean`. Positive TPI = cell sits above its
   local surroundings (ridge/convex, more wind-exposed); negative = below
   surroundings (valley/concave, sheltered); near zero = flat or
   uniform-slope terrain (average exposure).

Exported as `exposure_index.tif` (continuous, like `wetness_index.tif` --
no natural small code set to reclassify onto) and `exposure_index.npy`.

## Neighborhood radius
`EXPOSURE_RADIUS_CELLS = 15` (150 m at the current 10 m `CELL_SIZE_M`) --
a judgment call, not a validated scale. Chosen to characterize *local*
topographic position (this stand vs. its immediate surroundings) rather
than macro-landform (this valley vs. the whole mountain range), and picked
to numerically match `red_ring_rot["max_dispersal_distance_m"]` (150 m) so
the exposure signal is characterized at roughly the same spatial scale the
pathogen's own dispersal kernel operates at -- a reasonable anchor, though
not a strict physical requirement (there's no reason the two must match;
it's a convenient, defensible-on-read-through choice, not a derived
constant, and would need its own justification if the two config values
ever diverge for unrelated reasons).

`arcpy.sa.FocalStatistics`'s default `ignore_nodata=True` means the focal
mean is computed from whatever valid cells fall within the window even
near the AOI boundary (unlike `Slope`/`Aspect`, which need a full 3x3
neighborhood and go NoData if any neighbor is NoData) -- so this doesn't
introduce a *wider* NoData band than the DEM's own. `TPI` is still NoData
wherever the source DEM cell itself is NoData (can't compute
`elevation - focal_mean` without an elevation), so it inherits the same
~3.5% AOI-edge band already seen in slope/aspect/TWI.

## NoData handling
Read with `nodata_to_value=np.nan` from the start (see
[[feedback-arcpy-float-nodata-sentinel]] -- this is now a known failure
mode for DEM-derived float rasters, caught the hard way during the wetness
work). In `load_site_grid`, `exposure` follows the exact same pattern as
`wetness`: per-site min-max normalize over finite cells only, NaN cells
scored neutral (0.5).

## Combination
Straight swap in `pathogens.py`, same shape as the wetness change:
`red_ring_rot["spatial_weights"]` drops `terrain`, adds `exposure` at the
same 0.35 weight. `terrain`/`score_terrain` stays in `spatial_inputs.py`
untouched and available, just with no current consumer in `pathogens.py`.
`spread_engine.py` needs no changes -- generic lookup by surface name, as
before.

## Assumptions
- TPI, not a directional exposure measure, is being used as a stand-in
  for "wind exposure" specifically because forestry windthrow-risk
  literature commonly uses topographic position/convexity as a
  direction-independent exposure predictor (ridges and convex slopes see
  higher wind speeds and more damage across most wind directions; valleys
  are sheltered regardless of which way the wind blows). This is a
  literature-grounded stand-in, not a site-specific validated model --
  same caveat as every other surface here.
- 150 m / 15-cell circular neighborhood is a judgment call (see above),
  not derived from any exposure/windthrow study specific to this site or
  species.
- Same weight (0.35) carried over from the old `terrain` entry, consistent
  with how the wetness swap was scoped -- replace the proxy, not
  re-tune the number, so the two judgment calls don't get conflated.

## Verification
Full real-data pipeline run for both sites (2026-09-04):

1. `export_site_layers.py` under ArcGIS Pro's Python -- both sites exported
   cleanly, no `ValueError`/shape mismatch, no schema-lock issue this time.
2. Applied the float-NoData fix from the start (`nodata_to_value=np.nan`
   on the new `exposure_index` raster, `normalize_surface_ignoring_nan`
   shared with `wetness`) rather than rediscovering the bug -- checked
   `exposure_index.npy` directly before trusting it: NaN fraction 2.5%
   (`site`)/2.51% (`site_phytophthora`), finite range roughly -69 to +114
   (`site`) and -16 to +59 (`site_phytophthora`) -- real elevation-
   difference magnitudes, no +/-3.4e38 sentinel. Slightly smaller NaN
   fraction than slope/aspect's ~3.5% (expected: `FocalStatistics`'s
   `ignore_nodata=True` only goes NoData where the source DEM cell itself
   is missing, not wherever any neighbor is, unlike `Slope`/`Aspect`'s
   full-3x3-neighborhood requirement).
3. `run_real_site_risk_raster.py` -- both pathogens computed without
   error:
   - `red_ring_rot`: risk range 0.000-0.420, mean 0.001 (changed from
     0.000-0.472, as expected -- its config changed).
   - `phytophthora`: risk range 0.000-0.07907 (exact), mean 1.057e-05
     (exact) -- matches the prior wetness-index verification's recorded
     0.000-0.079 to displayed precision. `git status` showed this file as
     modified, but that's a stale-baseline artifact (the last commit
     predates the wetness-index fix from earlier this session, not this
     change) -- not a usable regression signal here. Confirmed instead by
     reading `spread_engine.compute_risk_raster`: it only reads
     `environment[name]` for names in a pathogen's own `spatial_weights`,
     and `phytophthora`'s doesn't include `exposure`, so this change is
     structurally inert for it, not just observed-unchanged.
4. Compared `exposure` against the old `terrain` surface directly, per the
   contract's success criterion:
   - `site`: terrain mean 0.626, exposure mean 0.382; 89.6% of cells
     differ by >0.05; correlation -0.195.
   - `site_phytophthora`: terrain mean 0.589, exposure mean 0.216; 95.1%
     of cells differ by >0.05; correlation -0.044.
   Near-zero/slightly negative correlation confirms genuinely distinct
   signal, not a restatement of slope/aspect.
5. `import_risk_raster.py` under Pro's Python -- wrote both output
   GeoTIFFs without error.

## Update summary
- Contract, design note, `export_site_layers.py` TPI derivation
  (`FocalStatistics` + `NbrCircle`), `spatial_inputs.py` `exposure`
  surface, and `pathogens.py` reweight: all done this session.
- Refactored the wetness NaN-handling block from the previous feature into
  a shared `normalize_surface_ignoring_nan` helper in `spatial_inputs.py`,
  used by both `wetness` and `exposure` -- avoids duplicating the same
  NaN-aware min-max logic a second time now that it's a recurring pattern
  for DEM-derived float surfaces.
- Applied the float-NoData lesson from the wetness-index work proactively
  this time instead of rediscovering it -- verification checked the raw
  array for sentinel contamination before trusting any derived statistic.
- All contract success criteria met: no errors, `exposure` visibly
  distinct from `terrain`, `phytophthora` output confirmed unaffected
  (structurally, not just by observation).
- `terrain`/`score_terrain` now has no consumer in `pathogens.py` (neither
  pathogen references it) but is kept in `spatial_inputs.py` per the
  contract's non-goals, available for a future config.
- Remaining for next iteration: visually re-inspect both updated rasters
  in Pro (not yet done this session). The directional wind kernel (Part B
  of `wind_dispersal_and_soil_reweight.md`) is still blocked on real wind
  data -- TPI is a complement to that, not a substitute. `anthracnose`/
  `emerald_ash_borer`'s missing `spatial_weights` blocks remain the other
  open gap, not addressed here.

## Verification
