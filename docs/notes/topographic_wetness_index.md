# Design note: Topographic wetness index

## Approach
`export_terrain` in `export_site_layers.py` already produces a local DEM
clip (`dem.tif`) before deriving `Slope`/`Aspect` from it. TWI is computed
from that same local DEM, in the same function, via the standard
hydrologic chain (`arcpy.sa`):

1. `Fill(dem_local)` -- fills single-cell sinks so `FlowDirection` doesn't
   dead-end on DEM noise. Standard prerequisite step, not specific to TWI.
2. `FlowDirection(filled)` (D8, the default) -> `FlowAccumulation(flow_dir)`
   -- gives each cell a count of upslope cells draining into it.
3. Specific catchment area: `As = (flow_accumulation + 1) * cell_size_m`.
   The `+1` counts the cell's own unit contribution, a standard convention
   that also avoids `As = 0` at ridge/local-high cells (which have
   `flow_accumulation = 0`).
4. Slope, in radians, clamped to a minimum of 0.1 degrees before
   converting: `tan(0)` is 0, which would make `As / tan(slope)` divide by
   zero (undefined TWI) at any perfectly flat cell. 0.1 degrees is a small
   enough floor to not distort real slope values while keeping the ratio
   finite -- flat cells still register as "high wetness" (very large
   `As/tan`), which is directionally correct for TWI (flat, low terrain is
   exactly where water pools) rather than an artifact to hide.
5. `TWI = Ln(As / Tan(slope_clamped_radians))`.

Exported as `wetness_index.tif` (continuous, not reclassified -- unlike the
categorical soil surfaces, there's no natural small code set to map onto)
and `wetness_index.npy`, alongside the existing slope/aspect outputs.

## Normalization and combination
`spatial_inputs.load_site_grid` gets a new `wetness` key: per-site min-max
normalize the raw TWI array (`normalize_surface`, same pattern as
`water_table_depth_in` and every other continuous surface in this module)
-- no inversion, since higher TWI already means "more water accumulates
here," which is directionally what "higher wetness suitability" should
mean for phytophthora.

This is a straight swap in `pathogens.py`, not a new combination: `terrain`
stays defined (still used by `red_ring_rot`) and unchanged code-wise;
`phytophthora["spatial_weights"]` drops the `terrain` key and adds
`wetness` at the same 0.25 weight. `spread_engine.py` needs no changes --
it already looks up whatever surface names appear in a pathogen's
`spatial_weights` from the environment dict generically.

## Assumptions
- D8 flow direction (single steepest-descent neighbor) rather than a
  multi-flow-direction algorithm -- `arcpy.sa.FlowDirection`'s default and
  the standard choice for TWI in the literature; a multi-flow-direction
  variant would give smoother contributing-area estimates but isn't
  available as a simple built-in swap in Spatial Analyst.
- 0.1-degree minimum slope floor is a judgment call, not a validated
  threshold -- chosen to be well below any real slope signal at 10 m
  resolution while keeping the math finite.
- AOI-edge underestimation (see contract non-goals) is left uncorrected --
  the 2 km clip means cells near the boundary don't see upslope
  contributing area from outside the clip. Real known-case points sit
  roughly centered in each AOI (per `build_aoi_extent`), so this mainly
  affects the AOI's outer margin, not the area immediately around the
  known cases that matters most for the risk raster's footprint.
- Same weight (0.25) carried over from the old `terrain` entry rather than
  re-deriving a new number -- the contract scope is "replace the proxy,"
  not "re-tune the weight," so changing both at once would conflate two
  different judgment calls.

## Verification
Full real-data pipeline run for both sites (2026-09-04):

1. `export_site_layers.py` under ArcGIS Pro's Python -- both sites exported
   cleanly, no `ValueError`/shape mismatch. First `import_risk_raster.py`
   run hit the same schema-lock pattern as
   [[feedback-arcpy-schema-lock-open-map]] (`phytophthora_site_risk.tif`
   still loaded as a layer in Pro from eyeballing an earlier preview);
   resolved by removing the layer, re-run succeeded.

2. **Bug found and fixed during verification, not in the original
   implementation pass.** `arcpy.RasterToNumPyArray` on a float raster
   defaults NoData cells to the dtype's min/max representable float
   (~+/-3.4e38) when no `nodata_to_value` is given. `slope_degrees.npy` and
   `aspect_degrees.npy` (float rasters from `Slope`/`Aspect`) both carried
   this sentinel at ~3.5% of cells -- a thin NoData band at the AOI edge
   left by the DEM's bilinear reprojection. This was already silently
   present before this feature (score_terrain's `clip()` happened to absorb
   it at those edge cells without erroring), but it went uncaught until the
   new `wetness_index.npy` inherited the same issue and *visibly* broke:
   `normalize_surface`'s global min/max got dominated by the sentinel,
   compressing nearly all real cells into a narrow band near 1.0 (initial
   run showed wetness mean 0.964, immediately suspicious against a raw TWI
   percentile check). Fixed by reading slope/aspect/wetness with
   `nodata_to_value=np.nan` at export time, then treating NaN as neutral
   (0.5) in both `score_terrain` (mirroring the existing flat-aspect `-1`
   special case) and the wetness normalization (excluded from min/max,
   scored 0.5). Re-exported and recomputed after the fix; raw wetness
   percentiles and the final normalized distribution are now sane (see
   below).

3. `run_real_site_risk_raster.py` (plain `.venv`) -- both pathogens
   computed without error, post-fix:
   - `red_ring_rot`: risk range 0.000-0.472, mean 0.001 -- and confirmed
     via `git status` that `outputs/red_ring_rot_site_risk.npy` (plus
     `_grid_meta.json`, `.tif`, and the preview PNG) are byte-identical to
     the last commit, both before and after the NaN fix. Clean regression:
     the phytophthora-only config swap and the slope/aspect NaN fix didn't
     leak into red_ring_rot's output at all.
   - `phytophthora`: risk range 0.000-0.079, mean 0.000.

4. Compared the new `wetness` surface against the old `terrain` surface
   directly on real data, per the contract's success criterion:
   - `site`: terrain mean 0.626, wetness mean 0.228; 93.2% of cells differ
     by >0.05; correlation 0.260.
   - `site_phytophthora`: terrain mean 0.589, wetness mean 0.289; 89.2% of
     cells differ by >0.05; correlation -0.155.
   Low/near-zero correlation plus a plausible right-skewed wetness
   distribution (most cells low-moderate, a smaller high-wetness tail near
   flat/high-accumulation cells) confirms this is genuinely distinct
   signal, not a restatement of slope/aspect.

5. `import_risk_raster.py` under Pro's Python -- wrote both output
   GeoTIFFs without error after the schema-lock was cleared. Not yet
   visually re-inspected in Pro since the fix (the pre-fix rasters were
   already loaded and looked fine, but the underlying wetness values have
   changed since) -- worth a fresh look next time Pro's open.

## Update summary
- Contract, design note, `export_site_layers.py` TWI derivation,
  `spatial_inputs.py` wetness surface, and `pathogens.py` reweight: all
  done this session.
- Bug fix (NaN-safe NoData handling for slope/aspect/wetness): done this
  session, caught during verification rather than shipped silently. Also
  retroactively fixes a latent, previously-uncaught inaccuracy in the
  existing `terrain` surface at AOI-edge cells (~3.5% of each site's
  cells), which predates this feature.
- Full pipeline run and all contract success criteria met: no errors,
  `wetness` visibly distinct from `terrain`, `red_ring_rot` output
  byte-identical (regression-clean).
- New memory saved: [[feedback-arcpy-schema-lock-open-map]] (recurrence of
  the schema-lock issue) -- worth adding a similar memory for the float
  NoData sentinel behavior if it recurs on a future terrain-derived surface.
- Remaining for next iteration: re-inspect the updated
  `phytophthora_site_risk.tif` visually in Pro (values changed post-fix,
  not yet re-eyeballed). Beyond that, this feature is done. The
  wind-exposure proxy (`red_ring_rot`'s `terrain`) remains an open
  improvement opportunity per the contract's non-goals, not pursued here.
