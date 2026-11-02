# Design note: Topographic position index (wind exposure)

## Approach
`export_terrain` gains a fourth derived raster. It sits alongside slope, aspect, and TWI. It is computed from the same local DEM clip (`dem.tif`):

1. `arcpy.sa.FocalStatistics(dem_local, neighborhood, "MEAN")` gives the mean elevation within a circular neighborhood around each cell. `arcpy.sa.NbrCircle(EXPOSURE_RADIUS_CELLS, "CELL")` defines the neighborhood. The radius is in cells, not map units. So it scales correctly with `CELL_SIZE_M`.
2. `TPI = dem_local - focal_mean`. A positive TPI means the cell sits above its local surroundings. That is ridge or convex terrain, which is more wind-exposed. A negative TPI means the cell sits below its surroundings. That is valley or concave terrain, which is sheltered. A value near zero means flat or uniform-slope terrain, with average exposure.

The result is exported as `exposure_index.tif` and `exposure_index.npy`. Like `wetness_index.tif`, it is continuous. There is no natural small code set to reclassify onto.

## Neighborhood radius
`EXPOSURE_RADIUS_CELLS = 15`, which is 150 m at the current 10 m `CELL_SIZE_M`. This is a judgment call, not a validated scale.

The radius characterizes local topographic position. That means this stand compared with its immediate surroundings. It does not characterize macro-landform, such as this valley compared with the whole mountain range.

The value was chosen to match `red_ring_rot["max_dispersal_distance_m"]` (150 m). The exposure signal is then measured at about the same spatial scale as the pathogen's dispersal kernel. This is a reasonable anchor. It is not a strict physical requirement. Nothing requires the two values to match. It is a convenient, defensible choice, not a derived constant. It would need its own justification if the two config values ever diverged for unrelated reasons.

`arcpy.sa.FocalStatistics` defaults to `ignore_nodata=True`. So the focal mean uses whatever valid cells fall in the window, even near the AOI boundary. `Slope` and `Aspect` need a full 3x3 neighborhood, and they go NoData if any neighbor is NoData. So this step does not create a wider NoData band than the DEM's own.

`TPI` is still NoData wherever the source DEM cell is NoData. It cannot compute `elevation - focal_mean` without an elevation. So it inherits the same AOI-edge band of about 3.5% already seen in slope, aspect, and TWI.

## NoData handling
The raster is read with `nodata_to_value=np.nan` from the start. See [[feedback-arcpy-float-nodata-sentinel]]. This is a known failure mode for DEM-derived float rasters. The wetness work caught it the hard way.

In `load_site_grid`, `exposure` follows the same pattern as `wetness`. It is min-max normalized over finite cells only. NaN cells are scored as neutral (0.5).

## Combination
This is a straight swap in `pathogens.py`, the same shape as the wetness change. `red_ring_rot["spatial_weights"]` drops `terrain` and adds `exposure` at the same 0.35 weight.

`terrain` and `score_terrain` stay in `spatial_inputs.py`, untouched and available. They have no current consumer in `pathogens.py`. `spread_engine.py` needs no changes. It uses a generic lookup by surface name, as before.

## Assumptions
- TPI is used as a stand-in for "wind exposure." It is not a directional exposure measure. The reason is that forestry windthrow literature often uses topographic position or convexity as a direction-independent exposure predictor. Ridges and convex slopes see higher wind speeds and more damage across most wind directions. Valleys are sheltered regardless of wind direction. This is a literature-based stand-in, not a validated model for this site. It carries the same caveat as every other surface in this project.
- The 150 m, 15-cell circular neighborhood is a judgment call (see above). It is not derived from any exposure or windthrow study for this site or species.
- The same weight (0.35) carries over from the old `terrain` entry. This matches the wetness swap. The proxy is replaced, not the number, so the two judgment calls stay separate.

## Verification
Full real-data pipeline run for both sites (2026-09-04):

1. `export_site_layers.py` under ArcGIS Pro's Python. Both sites exported cleanly, with no `ValueError` and no shape mismatch. There was no schema lock this time.
2. The float-NoData fix was applied from the start. The new `exposure_index` raster is read with `nodata_to_value=np.nan`, and `normalize_surface_ignoring_nan` (shared with `wetness`) normalizes it. The raw array was checked before any derived statistic was trusted:
   - NaN fraction: 2.5% (`site`) and 2.51% (`site_phytophthora`).
   - Finite range: about -69 to +114 (`site`), and -16 to +59 (`site_phytophthora`). These are real elevation-difference magnitudes. There is no +/-3.4e38 sentinel.

   The NaN fraction is slightly smaller than the roughly 3.5% for slope and aspect. This is expected. `FocalStatistics` with `ignore_nodata=True` goes NoData only where the source DEM cell itself is missing. `Slope` and `Aspect` go NoData wherever any neighbor is missing, because they need the full 3x3 neighborhood.
3. `run_real_site_risk_raster.py` computed both pathogens without error.
   - `red_ring_rot`: range 0.000-0.420, mean 0.001. This changed from 0.000-0.472, as expected, because its config changed.
   - `phytophthora`: range 0.000-0.07907 (exact), mean 1.057e-05 (exact). This matches the earlier wetness-index verification (0.000-0.079) at displayed precision.

     `git status` showed this file as modified. That is a stale-baseline artifact. The last commit predates the wetness-index fix from earlier this session, not this change. So it is not a usable regression signal here. The check was done by reading `spread_engine.compute_risk_raster` instead. It reads `environment[name]` only for names in a pathogen's own `spatial_weights`. The `phytophthora` `spatial_weights` does not include `exposure`. So this change has no effect on it. The result is structural, not only observed.
4. The `exposure` surface was compared directly with the old `terrain` surface. This meets the contract's success criterion.
   - `site`: terrain mean 0.626, exposure mean 0.382. 89.6% of cells differ by more than 0.05. Correlation -0.195.
   - `site_phytophthora`: terrain mean 0.589, exposure mean 0.216. 95.1% of cells differ by more than 0.05. Correlation -0.044.

   A near-zero or slightly negative correlation confirms a distinct signal. It is not a restatement of slope and aspect.
5. `import_risk_raster.py` under Pro's Python wrote both GeoTIFFs without error.

## Update summary
- Contract, design note, the `export_site_layers.py` TPI derivation (`FocalStatistics` and `NbrCircle`), the `spatial_inputs.py` `exposure` surface, and the `pathogens.py` reweight: all done this session.
- The wetness NaN-handling block from the previous feature was refactored into a shared `normalize_surface_ignoring_nan` helper in `spatial_inputs.py`. Both `wetness` and `exposure` use it. This avoids a second copy of the same NaN-aware min-max logic. The pattern now recurs for DEM-derived float surfaces.
- The float-NoData lesson from the wetness-index work was applied up front this time. Verification checked the raw array for sentinel contamination before trusting any derived statistic.
- All contract success criteria are met. There are no errors. `exposure` is visibly distinct from `terrain`. The `phytophthora` output is confirmed unaffected, structurally and not only by observation.
- `terrain` and `score_terrain` now have no consumer in `pathogens.py`. Neither pathogen references them. They stay in `spatial_inputs.py` per the contract's non-goals, available for a future config.
- Remaining for next iteration: visually re-inspect both updated rasters in Pro. This is not done yet. The directional wind kernel (Part B of `wind_dispersal_and_soil_reweight.md`) is still blocked on real wind data. TPI complements that work. It does not replace it. `anthracnose` and `emerald_ash_borer` still have missing `spatial_weights` blocks. That is the other open gap, and it is not addressed here.

## Verification
