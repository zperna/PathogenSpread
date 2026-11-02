# Feature contract: Topographic position index for red ring rot's wind-exposure proxy

## Problem
`red_ring_rot["spatial_weights"]["terrain"] = 0.35` is the largest single spatial weight in that config. `pathogens.py` documents it as "our current proxy for wind exposure." It supports a pathogen whose transmission depends on wind-dispersed spores that infect through wounds (see `docs/feature_contracts/wind_dispersal_and_soil_reweight.md`).

The proxy itself is `spatial_inputs.score_terrain`. It combines moderate-slope favorability with north-facing aspect. It is a generic terrain score. It makes no specific claim to represent wind exposure. The earlier contract flagged it as a placeholder.

`docs/feature_contracts/topographic_wetness_index.md` flagged it again as an open non-goal: "No attempt to improve the wind-exposure proxy itself... out of scope here, a separate future contract if pursued." That note was written when phytophthora's matching `terrain` weight moved to a purpose-built topographic wetness index. Phytophthora no longer uses the same generic score.

A real directional wind-exposure measure would need prevailing wind direction and strength data. That data does not exist for this site. It is a blocked dependency, "Part B", in `wind_dispersal_and_soil_reweight.md`.

Direction is not the only factor that predicts wind exposure or damage in forestry. **Topographic position** is another. It describes whether a cell sits on a ridge or convex landform, which is exposed to wind from most directions. It also describes whether a cell sits in a valley or concave landform, which is sheltered. Topographic position is a well-established proxy for wind exposure and windthrow risk. It does not depend on direction. It can be derived from the DEM this project already exports, the same way TWI was derived for wetness.

## Goal
Add a DEM-derived Topographic Position Index (TPI) surface as an `exposure` measure. Use it as `red_ring_rot`'s terrain-proxy weight in place of the generic slope and aspect score.

This is the same kind of per-pathogen swap made for phytophthora and wetness. It does not change `score_terrain` itself. It does not change any other pathogen's config.

## Scope
- In `export_site_layers.py`'s `export_terrain`, derive TPI from the local DEM clip (`dem.tif`). Do this in the same function as slope, aspect, and TWI. The DEM is already local at that point. The formula is `TPI = elevation - focal_mean(elevation, neighborhood)`, computed with `arcpy.sa.FocalStatistics`. Export it alongside the existing rasters.
- Add a new `exposure` surface to `spatial_inputs.load_site_grid`. Min-max normalize the raw TPI array per site. Higher TPI (more ridge-like or convex) means more exposed, and so higher suitability for this pathogen. No inversion is needed. This follows the same pattern as `wetness`.
- Update `red_ring_rot["spatial_weights"]` in `pathogens.py`. Replace the `terrain` key with `exposure`, at the same 0.35 weight. This pass replaces the proxy, not the weight. This matches how the wetness swap handled its weight.
- Re-run the full pipeline (export, compute, import) for both sites.
- Apply the float-NoData handling from the wetness work to the new TPI raster from the start. That means `nodata_to_value=np.nan` and a neutral 0.5 fallback. This is now a known failure mode for any DEM-derived float surface (see [[feedback-arcpy-float-nodata-sentinel]]). Do not rediscover it.

## Non-goals
- `phytophthora` is not changed. It already uses `wetness`, not `terrain`.
- `terrain` and `score_terrain` are not removed or changed. They stay in `spatial_inputs.py` in case a future pathogen config wants a generic slope and aspect surface. After this change, they have no current consumer in `pathogens.py`. That is acceptable. They are infrastructure, not dead code slated for deletion.
- No directional wind kernel. It is still blocked on real wind data, per `wind_dispersal_and_soil_reweight.md` Part B. TPI is a direction-independent complement to that future work. It is not a substitute for it.
- No re-tuning of the 0.35 weight or of any other `red_ring_rot` parameter.
- This does not address the missing `spatial_weights` blocks for `anthracnose` or `emerald_ash_borer`. That is a separate gap, already identified. It is not pursued here.
- No claim is made that TPI-based exposure is a *validated* wind-exposure measure for this site or pathogen. It is a standard, literature-grounded terrain metric that stands in for a real driver. It carries the same caveat as every other suitability surface in this project.

## Inputs
- `data/<site>/gis_reference/dem.tif`, already exported. No new external data source is needed.

## Outputs
- `data/<site>/gis_reference/exposure_index.tif` (raw TPI, continuous).
- `data/<site>/exposure_index.npy`.
- The environment dict returned by `load_site_grid` gains an `exposure` key (0-1 normalized). It sits alongside the existing `terrain` key.
- `red_ring_rot["spatial_weights"]` now references `exposure` instead of `terrain`. `phytophthora` is unchanged.
- Updated `outputs/red_ring_rot_site_risk.npy`, `.tif`, and preview. The `phytophthora` output should not change numerically. This is a regression check. It mirrors how `red_ring_rot`'s output was checked byte-for-byte during the wetness-index work.

## Success criteria
- Both sites' exports run end to end, with no `ValueError` and no shape mismatch. The new raster has no float-NoData contamination. Check this directly with `np.isnan` and percentile statistics before trusting the normalized surface. The wetness-index work showed that this kind of error can produce a result that looks plausible but is wrong.
- The new `exposure` surface is visibly different from the existing `terrain` surface in each AOI. Check this directly. Do not rely on eyeballing the final raster.
- `phytophthora`'s risk raster output is numerically identical before and after this change. Ideally it is byte-identical, per `git status`.
- `run_real_site_risk_raster.py` and `import_risk_raster.py` still run cleanly for both pathogens.

## Definition of done
- This contract exists (done).
- The design note, implementation, verification, and update summary follow in `docs/notes/wind_exposure_index.md`.
