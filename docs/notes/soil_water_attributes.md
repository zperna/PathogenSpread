# Design note: Richer soil water attributes

## Approach
`export_site_layers.py`'s `export_soil_drainage` becomes
`export_soil_surfaces`: one `JoinField` call brings `drclassdcd`,
`hydgrpdcd`, and `wtdepannmin` onto the working raster copy in a single
pass (rather than three separate `CopyRaster`/`JoinField` round-trips),
then each field gets its own small reclassified/passed-through raster via
`Lookup`, reprojected the same way the existing drainage raster is.

### Hydrologic group encoding
`hydgrpdcd` values look like `"A"`..`"D"` or dual ratings like `"A/D"`
(soils with a seasonally high water table that would drain as the first
letter if artificially drained, but behave as the second letter under
natural conditions). Since nothing in this project's data represents
artificial drainage, dual ratings resolve to the second letter -- the
natural-condition rating. Mapped to an ordinal 0-1 score using the same
style as the existing `DRAINAGE_CLASS_SCORES` ramp: A (well-drained,
low runoff potential) scores low, D (poorly drained, high runoff/low
infiltration) scores high, consistent with "wetter/poorer infiltration =
more favorable to a soil-borne root pathogen."

### Water table depth encoding
`wtdepannmin` is already numeric (inches). Unlike the categorical fields,
`NULL` here is meaningful -- SSURGO records `NULL` when no water table
occurs within the reported depth range, i.e. "deep/not applicable," not
"missing data" in the usual sense. Filling that with 0 would be actively
wrong (0 means "water table at the surface," the opposite claim), so nulls
are filled with a large sentinel (200 inches -- comfortably beyond any
value seen in either AOI, max 76) before normalizing, so they land near 0
suitability after normalization rather than distorting the scale.

Score = `1 - normalize_surface(water_table_depth_in)` (per-site min-max
normalize, same pattern already used elsewhere in `spatial_inputs.py`) --
shallower water table -> higher suitability.

### Combining into one `soil` surface
`spatial_inputs.load_site_grid` now averages three 0-1 scores (drainage
class, hydrologic group, water table depth) unweighted into the `soil`
surface `compute_risk_raster` consumes. Kept as a simple mean rather than
introducing new tunable weights in this pass -- three real, independently-
sourced signals averaged together is still a judgment call (as any
combination would be), but it's no longer resting on one guessed 7-value
ramp alone.

## Assumptions
- Dual hydrologic-group ratings should resolve to natural (undrained)
  conditions -- reasonable for a wildland/forest site with no indication of
  engineered drainage, but not verified against the actual site.
- 200 inches is a safe "deep enough not to matter" sentinel for this
  region's data; would need revisiting if exported to a site with a
  genuinely deeper recorded water table.
- Equal-weighted averaging of the three soil signals is itself a
  simplification -- e.g. `wtdepannmin` arguably deserves more weight than
  `hydgrpdcd` since it's a more direct, less-aggregated measurement, but
  that's a further judgment call left for a future pass rather than
  smuggled in here without being called out.

## Verification
Full real-data pipeline run for both sites (2026-09-04):

1. `export_site_layers.py` under ArcGIS Pro's Python -- both `RedRingRot`
   and `Phytophthora` exported cleanly, no `ValueError`/shape mismatch (the
   pre-existing pixel-alignment crop still fires as expected, unrelated to
   this feature). First attempt hit an unrelated `ERROR 999999` /
   "Permission denied" deleting `landcover.tif` -- a schema lock
   (`.sr.lock`) held by ArcGIS Pro because that raster's layer was still
   loaded in the open project's map. Resolved by removing the layer in Pro;
   re-run succeeded. Confirmed `hydro_group_code.npy`,
   `water_table_depth_in.npy`, and `hydro_groups.json` now exist under both
   `data/site/` and `data/site_phytophthora/`.
2. `run_real_site_risk_raster.py` (plain `.venv`) -- both pathogens
   computed without error:
   - `red_ring_rot`: risk range 0.000-0.472, mean 0.001 (unaffected by this
     feature, as expected -- no `soil` weight).
   - `phytophthora`: risk range 0.000-0.098, mean 0.000.
3. Compared the new combined `soil` surface against the old drainage-only
   surface directly (not just eyeballing the risk raster), per the
   contract's success criterion, on the real exported grids:
   - `site` (RedRingRot AOI): mean shifted 0.415 -> 0.681; 73.7% of cells
     differ by >0.05.
   - `site_phytophthora`: mean shifted 0.363 -> 0.175; 68.8% of cells
     differ by >0.05.
   Confirms the new fields are contributing real, non-duplicate signal
   across most of both AOIs, not just in a few cells.
4. `import_risk_raster.py` under Pro's Python -- wrote
   `outputs/red_ring_rot_site_risk.tif` and
   `outputs/phytophthora_site_risk.tif` without error. Not yet loaded into
   `PathogenProject.aprx` for a visual sanity check in Pro -- that's a
   manual step for the user (per [[feedback-arcpy-headless-save-hangs]],
   nothing here scripts `aprx.save()`).

What was verified in an earlier session, with plain `.venv` Python and
synthetic stand-in data (no arcpy needed, since `load_site_grid`'s new
averaging logic in `spatial_inputs.py` only consumes already-exported
`.npy`/`.json` files): built a small 5x5 fake site grid with one half coded
well-drained / hydrologic group A / deep (sentinel) water table, the other
half poorly-drained / group D / shallow water table, and confirmed
`load_site_grid`'s combined `soil` surface scores the wet half (0.93) well
above the dry half (0.17) -- i.e. the three-signal average produces the
intended direction and isn't dominated or cancelled out by any one input.
This checks the combination math, not the real-data pipeline end to end.

## Update summary
- Contract and design note: done (prior session).
- `export_site_layers.py`: done (prior session) -- exports
  `soil_hydro_group`/`soil_water_table_depth` alongside the existing
  drainage raster, writes `hydro_group_code.npy`, `water_table_depth_in.npy`,
  `hydro_groups.json`, and fills water-table NoData with the 200in sentinel
  via `raster_to_bottom_up_array`'s new `nodata_to_value` param.
- `spatial_inputs.py` (this session): added `HYDRO_GROUP_SCORES` (A=0.15 ..
  D=0.90, same ordinal style as `DRAINAGE_CLASS_SCORES`); `load_site_grid`
  now loads `hydro_groups.json` and the two new `.npy` files, scores each of
  the three soil signals (drainage class, hydrologic group,
  `1 - normalize_surface(water_table_depth)`), and averages them unweighted
  into `soil`. No changes needed in `spread_engine.py`/`pathogens.py` --
  `soil` is looked up generically by name from `spatial_weights`.
- Full pipeline run (this session): export -> compute -> import all
  succeeded for both sites; combined `soil` surface confirmed to visibly
  differ from the old drainage-only surface on real data (see Verification).
  All success criteria in the contract are now met.
- Remaining for next iteration: load `outputs/red_ring_rot_site_risk.tif`
  and `outputs/phytophthora_site_risk.tif` into `PathogenProject.aprx` in
  the Pro UI for a visual sanity check -- manual step, not scripted here.
  Beyond that, this feature is done; `wtdepaprjunmin`, `flodfreqdcd`,
  `pondfreqprs`, `drclasswettest`, `aws0100wta` remain documented
  candidates for a future pass per the contract's non-goals.
