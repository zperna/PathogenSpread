# Design note: Topographic wetness index

## Approach
`export_terrain` in `export_site_layers.py` already produces a local DEM clip (`dem.tif`). It does this before it derives `Slope` and `Aspect` from that clip. TWI is computed from the same local DEM, in the same function, through the standard hydrologic chain (`arcpy.sa`):

1. `Fill(dem_local)` fills single-cell sinks. This keeps `FlowDirection` from dead-ending on DEM noise. It is a standard prerequisite step. It is not specific to TWI.
2. `FlowDirection(filled)` (D8, the default), then `FlowAccumulation(flow_dir)`. This gives each cell a count of the upslope cells that drain into it.
3. Specific catchment area: `As = (flow_accumulation + 1) * cell_size_m`. The `+1` counts the cell's own unit contribution. This is a standard convention. It also avoids `As = 0` at ridge or local-high cells, which have `flow_accumulation = 0`.
4. Slope, in radians, is clamped to a minimum of 0.1 degrees before conversion. `tan(0)` is 0. Without the clamp, `As / tan(slope)` would divide by zero at any perfectly flat cell, and TWI would be undefined. A 0.1 degree floor is small enough not to distort real slope values. It keeps the ratio finite.

   Flat cells still register as high wetness (a very large `As/tan`). This is directionally correct for TWI. Flat, low terrain is exactly where water pools. It is not an artifact to hide.
5. `TWI = Ln(As / Tan(slope_clamped_radians))`.

TWI is exported as `wetness_index.tif` and `wetness_index.npy`, alongside the existing slope and aspect outputs. It is continuous and not reclassified. Unlike the categorical soil surfaces, there is no natural small code set to map onto.

## Normalization and combination
`spatial_inputs.load_site_grid` gets a new `wetness` key. It min-max normalizes the raw TWI array per site (`normalize_surface`). This is the same pattern used for `water_table_depth_in` and every other continuous surface in this module. There is no inversion. A higher TWI already means more water collects here. That is what "higher wetness suitability" should mean for phytophthora.

This is a straight swap in `pathogens.py`, not a new combination. `terrain` stays defined and its code is unchanged, since `red_ring_rot` still uses it. `phytophthora["spatial_weights"]` drops the `terrain` key and adds `wetness` at the same 0.25 weight. `spread_engine.py` needs no changes. It already looks up any surface name in a pathogen's `spatial_weights` from the environment dict, generically.

## Assumptions
- D8 flow direction is used (one steepest-descent neighbor), not a multi-flow-direction algorithm. D8 is `arcpy.sa.FlowDirection`'s default and the standard choice for TWI in the literature. A multi-flow-direction variant would give smoother contributing-area estimates. It is not available as a simple built-in swap in Spatial Analyst.
- The 0.1-degree minimum slope floor is a judgment call. It is not a validated threshold. It sits well below any real slope signal at 10 m resolution, and it keeps the math finite.
- AOI-edge underestimation (see the contract's non-goals) is not corrected. The 2 km clip means cells near the boundary do not see upslope contributing area from outside the clip. Real known-case points sit roughly centered in each AOI (per `build_aoi_extent`). So this mainly affects the outer margin of the AOI. It does not affect the area right around the known cases, which matters most for the risk raster's footprint.
- The same weight (0.25) carries over from the old `terrain` entry. It was not re-derived. The contract scope is to replace the proxy, not to re-tune the weight. Changing both at once would mix two different judgment calls.

## Verification
Full real-data pipeline run for both sites (2026-09-04):

1. `export_site_layers.py` under ArcGIS Pro's Python. Both sites exported cleanly, with no `ValueError` and no shape mismatch. The first `import_risk_raster.py` run hit the same schema-lock pattern as [[feedback-arcpy-schema-lock-open-map]]. `phytophthora_site_risk.tif` was still loaded as a layer in Pro, from an earlier preview check. Removing the layer fixed it, and the re-run succeeded.

2. **Bug found and fixed during verification. It was not in the original implementation pass.** `arcpy.RasterToNumPyArray` on a float raster fills NoData cells with the dtype's min or max representable float (about +/-3.4e38) when no `nodata_to_value` is given.

   `slope_degrees.npy` and `aspect_degrees.npy` (float rasters from `Slope` and `Aspect`) both carried this sentinel in about 3.5% of cells. That is a thin NoData band at the AOI edge, left by the DEM's bilinear reprojection. The problem existed before this feature. `score_terrain`'s `clip()` absorbed it at those edge cells without an error. It went uncaught until the new `wetness_index.npy` inherited the same issue, and then it visibly broke. `normalize_surface`'s global min and max were dominated by the sentinel. Nearly all real cells compressed into a narrow band near 1.0. The first run showed a wetness mean of 0.964. That was immediately suspicious against a raw TWI percentile check.

   The fix reads slope, aspect, and wetness with `nodata_to_value=np.nan` at export time. NaN is then treated as neutral (0.5). This applies in two places. The first is `score_terrain`, which mirrors the existing flat-aspect `-1` special case. The second is the wetness normalization, which excludes NaN from min and max and scores those cells 0.5. The rasters were re-exported and recomputed after the fix. The raw wetness percentiles and the final normalized distribution are now sane (see below).

3. `run_real_site_risk_raster.py` (plain `.venv`). Both pathogens computed without error after the fix.
   - `red_ring_rot`: range 0.000-0.472, mean 0.001. `git status` confirmed that `outputs/red_ring_rot_site_risk.npy` (plus `_grid_meta.json`, `.tif`, and the preview PNG) are byte-identical to the last commit. This holds both before and after the NaN fix. This is a clean regression result. The phytophthora-only config swap and the slope and aspect NaN fix did not change `red_ring_rot`'s output at all.
   - `phytophthora`: range 0.000-0.079, mean 0.000.

4. The new `wetness` surface was compared with the old `terrain` surface on real data. This meets the contract's success criterion.
   - `site`: terrain mean 0.626, wetness mean 0.228. 93.2% of cells differ by more than 0.05. Correlation 0.260.
   - `site_phytophthora`: terrain mean 0.589, wetness mean 0.289. 89.2% of cells differ by more than 0.05. Correlation -0.155.

   Low or near-zero correlation confirms a distinct signal. The wetness distribution is right-skewed as expected. Most cells are low to moderate. A smaller high-wetness tail sits near flat or high-accumulation cells. So the signal is not a restatement of slope and aspect.

5. `import_risk_raster.py` under Pro's Python wrote both output GeoTIFFs without error, after the schema lock was cleared. The rasters have not been checked visually in Pro since the fix. The pre-fix rasters were already loaded and looked fine. But the wetness values have changed since then. They should be checked again the next time Pro is open.

## Update summary
- Contract, design note, the `export_site_layers.py` TWI derivation, the `spatial_inputs.py` wetness surface, and the `pathogens.py` reweight: all done this session.
- NaN-safe NoData handling for slope, aspect, and wetness: done this session. It was caught during verification, not shipped silently. It also fixes an older, unnoticed error in the existing `terrain` surface at AOI-edge cells (about 3.5% of each site's cells). That error predates this feature.
- Full pipeline run done. All contract success criteria are met. There are no errors. `wetness` is visibly distinct from `terrain`. The `red_ring_rot` output is byte-identical (regression clean).
- New memory saved: [[feedback-arcpy-schema-lock-open-map]], covering the recurrence of the schema-lock issue. A similar memory for the float NoData sentinel behavior may be worth saving if it recurs on a future terrain-derived surface.
- Remaining for next iteration: re-inspect the updated `phytophthora_site_risk.tif` visually in Pro. Its values changed after the fix and have not been re-checked. Beyond that, the feature is done. The wind-exposure proxy (`red_ring_rot`'s `terrain`) remains an open improvement opportunity. It is listed in the contract's non-goals and was not pursued here.
