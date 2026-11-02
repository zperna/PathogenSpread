# Design note: Richer soil water attributes

## Approach
`export_site_layers.py`'s `export_soil_drainage` becomes `export_soil_surfaces`. One `JoinField` call brings `drclassdcd`, `hydgrpdcd`, and `wtdepannmin` onto the working raster copy in a single pass. The earlier approach used three separate `CopyRaster` and `JoinField` round trips.

Each field then gets its own small reclassified or passed-through raster through `Lookup`. Each one is reprojected the same way the existing drainage raster is.

### Hydrologic group encoding
`hydgrpdcd` values look like `"A"` through `"D"`. Dual ratings look like `"A/D"`. A dual rating means the soil would drain as the first letter if it were artificially drained. Under natural conditions it behaves as the second letter.

Nothing in this project's data represents artificial drainage. So dual ratings resolve to the second letter, the natural-condition rating. Each group maps to an ordinal 0-1 score. The style matches the existing `DRAINAGE_CLASS_SCORES` ramp. A (well-drained, low runoff potential) scores low. D (poorly drained, high runoff and low infiltration) scores high. This matches the idea that wetter or poorer infiltration is more favorable to a soil-borne root pathogen.

### Water table depth encoding
`wtdepannmin` is already numeric (inches). Unlike the categorical fields, `NULL` has a meaning here. SSURGO records `NULL` when no water table occurs within the reported depth range. That means "deep or not applicable." It does not mean "missing data" in the usual sense.

Filling with 0 would be wrong. It would mean "water table at the surface," the opposite claim. So nulls are filled with a large sentinel of 200 inches. That value is well beyond any value seen in either AOI (max 76). The fill happens before normalizing. Nulls then land near 0 suitability and do not distort the scale.

The score is `1 - normalize_surface(water_table_depth_in)`. `normalize_surface` is a per-site min-max normalize. It is the same pattern already used elsewhere in `spatial_inputs.py`. A shallower water table gives a higher suitability.

### Combining into one `soil` surface
`spatial_inputs.load_site_grid` now averages three 0-1 scores with no weights. The three scores are drainage class, hydrologic group, and water table depth. The average is the `soil` surface that `compute_risk_raster` consumes.

This pass uses a simple mean, not new tunable weights. Averaging three real, separately sourced signals is still a judgment call, as any combination is. But the result no longer rests on one guessed 7-value ramp.

## Assumptions
- Dual hydrologic-group ratings should resolve to natural (undrained) conditions. This suits a wildland or forest site with no sign of engineered drainage. It has not been checked against the actual site.
- 200 inches is a safe "deep enough not to matter" sentinel for this region's data. It needs review if the method is applied to a site with a much deeper recorded water table.
- Equal-weighted averaging of the three soil signals is a simplification. For example, `wtdepannmin` may deserve more weight than `hydgrpdcd`. It is a more direct, less aggregated measurement. That is a further judgment call. It is left for a future pass. It is named here, not hidden.

## Verification
Full real-data pipeline run for both sites (2026-09-04):

1. `export_site_layers.py` under ArcGIS Pro's Python. Both `RedRingRot` and `Phytophthora` exported cleanly. There was no `ValueError` and no shape mismatch. The pre-existing pixel-alignment crop still ran as expected. It is unrelated to this feature.

   The first attempt hit an unrelated `ERROR 999999` ("Permission denied") while deleting `landcover.tif`. This was a schema lock (`.sr.lock`) held by ArcGIS Pro. The raster's layer was still loaded in the open project's map. Removing the layer in Pro fixed it, and the re-run succeeded.

   `hydro_group_code.npy`, `water_table_depth_in.npy`, and `hydro_groups.json` now exist under both `data/site/` and `data/site_phytophthora/`.
2. `run_real_site_risk_raster.py` (plain `.venv`). Both pathogens computed without error.
   - `red_ring_rot`: range 0.000-0.472, mean 0.001. This is unaffected by the feature, as expected. It has no `soil` weight.
   - `phytophthora`: range 0.000-0.098, mean 0.000.
3. The new combined `soil` surface was compared directly with the old drainage-only surface. This meets the contract's success criterion. The comparison used the real exported grids, not the risk raster.
   - `site` (RedRingRot AOI): mean moved from 0.415 to 0.681. 73.7% of cells differ by more than 0.05.
   - `site_phytophthora`: mean moved from 0.363 to 0.175. 68.8% of cells differ by more than 0.05.

   The new fields add real, non-duplicate signal across most of both AOIs. The change is not limited to a few cells.
4. `import_risk_raster.py` under Pro's Python. It wrote `outputs/red_ring_rot_site_risk.tif` and `outputs/phytophthora_site_risk.tif` without error. Neither raster is loaded into `PathogenProject.aprx` yet for a visual check in Pro. That is a manual step for the user. Per [[feedback-arcpy-headless-save-hangs]], nothing here scripts `aprx.save()`.

What was verified in an earlier session. This used plain `.venv` Python and synthetic stand-in data. No arcpy was needed, because `load_site_grid`'s new averaging logic in `spatial_inputs.py` only consumes already-exported `.npy` and `.json` files. A small 5x5 fake site grid was built.
- One half is coded well-drained, hydrologic group A, and deep (sentinel) water table.
- The other half is poorly drained, group D, and shallow water table.

`load_site_grid`'s combined `soil` surface scores the wet half (0.93) well above the dry half (0.17). So the three-signal average gives the intended direction. No single input dominates or cancels the others. This checks the combination math, not the real-data pipeline end to end.

## Update summary
- Contract and design note: done (prior session).
- `export_site_layers.py`: done (prior session). It exports `soil_hydro_group` and `soil_water_table_depth` alongside the existing drainage raster. It writes `hydro_group_code.npy`, `water_table_depth_in.npy`, and `hydro_groups.json`. It fills water-table NoData with the 200 in sentinel, using the new `nodata_to_value` parameter of `raster_to_bottom_up_array`.
- `spatial_inputs.py` (this session): added `HYDRO_GROUP_SCORES` (A=0.15 through D=0.90, same ordinal style as `DRAINAGE_CLASS_SCORES`). `load_site_grid` now loads `hydro_groups.json` and the two new `.npy` files. It scores each of the three soil signals: drainage class, hydrologic group, and `1 - normalize_surface(water_table_depth)`. It then averages them with no weights into `soil`.
- No changes were needed in `spread_engine.py` or `pathogens.py`. `soil` is looked up generically by name from `spatial_weights`.
- Full pipeline run (this session): export, compute, and import all succeeded for both sites. The combined `soil` surface visibly differs from the old drainage-only surface on real data. See Verification. All success criteria in the contract are now met.
- Remaining for next iteration: load `outputs/red_ring_rot_site_risk.tif` and `outputs/phytophthora_site_risk.tif` into `PathogenProject.aprx` in the Pro UI for a visual check. This is a manual step, not scripted. Beyond that, the feature is done. `wtdepaprjunmin`, `flodfreqdcd`, `pondfreqprs`, `drclasswettest`, and `aws0100wta` remain documented candidates for a future pass, per the contract's non-goals.
