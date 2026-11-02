# Feature contract: Anthracnose real-site risk raster

## Problem
`anthracnose` has no `spatial_weights` block in `pathogens.py`. This is the
same functional gap that `phytophthora` had before
`docs/feature_contracts/wind_dispersal_and_soil_reweight.md` fixed it.
`compute_risk_raster` needs at least one `spatial_weights` surface in the
environment grid to set the raster's shape. So `anthracnose` cannot run against
a real site raster today. It runs only against synthetic data, through `compute_risk`.

The real-site pipeline (`export_site_layers.py` -> `fetch_wind_rose.py` ->
`run_real_site_risk_raster.py`) knows about only two known-case feature classes:
`RedRingRot` and `Phytophthora`. The user is creating a third, `Anthracnose`,
with real confirmed cases.

## Goal
Give `anthracnose` a `spatial_weights` block. Reason it through the pathogen's
own transmission biology, not copied from another pathogen. Then wire a third
site, `data/site_anthracnose/`, through the existing real-site pipeline. Reuse
all of the pipeline unchanged. `Phytophthora` was added the same way, alongside `RedRingRot`.

## Scope
- `pathogens.py`: add `anthracnose["spatial_weights"]`. Anthracnose spreads by
  wind and rain splash, from canopy to canopy, over a short range
  (`max_dispersal_distance_m` of 200 m). Its hosts are broadleaf trees: maple,
  oak, sycamore, and dogwood. This is a different mechanism from
  `red_ring_rot`'s wind-driven wound infection, which the `exposure` and TPI
  surface target. It is also different from `phytophthora`'s root contact.
  `land_cover` is the dominant driver. It stands for host canopy density, the medium the spread has to move through.
  `wetness` (TWI) stands in for the "cool wet spring conditions" driver in
  `environmental_triggers`. TWI is already used as a moisture accumulation proxy
  for `phytophthora`. Here it is a foliar humidity reading, not a root-zone reading.
  `exposure`, `terrain`, and `soil` are left out. Ridge wind exposure and soil
  drainage are not defensible drivers for rain-splash canopy spread at this range.
- `export_site_layers.py`: add `"Anthracnose": "site_anthracnose"` to
  `CASE_LAYERS`. No other change is needed. The export function already works for any known-case feature class.
- `run_real_site_risk_raster.py`: add
  `("anthracnose", "site_anthracnose", "anthracnose_site_risk")` to `RUNS`.
- `fetch_wind_rose.py`: add `"site_anthracnose"` to `SITE_NAMES`.
  `anthracnose`'s `transmission_mode` is `"airborne"`. So once its
  `wind_rose.json` exists, `run_real_site_risk_raster.py` feeds it into the
  wind-aware dispersal kernel (Part B of `wind_dispersal_and_soil_reweight.md`).
  No extra wiring is needed. The engine's existing `transmission_mode` gate handles it.

## Inputs
- A new `Anthracnose` point feature class in `PathogenProject.gdb`. It has the
  same schema as `RedRingRot` and `Phytophthora` (`tree_id`, `species`,
  `stress_index`, `infected`). The user creates and populates it.
- Everything else (NLCD, gNATSGO, the ODF DEM service, and the IEM wind API) is
  already wired. It needs no site-specific changes.

## Outputs
- `data/site_anthracnose/` (grid and known cases), and `outputs/
  anthracnose_site_risk.{npy,tif}` with a preview, once exported.
- `anthracnose["spatial_weights"]` in `pathogens.py`.

## Success criteria
- `compute_risk_raster` runs for `anthracnose` against `data/
  site_anthracnose/` with no `ValueError`. This closes the same gap that `phytophthora`'s missing block had.
- The `red_ring_rot` and `phytophthora` outputs are unchanged. This is the regression check.
- Once wind data exists for the new site, the anthracnose raster shows the same
  kind of downwind-elongated lobe already verified for `red_ring_rot`.

## Non-goals
- This does not address the missing `spatial_weights` for `emerald_ash_borer`.
  No feature class or real cases exist for it yet.
- `anthracnose["spatial_weights"]` is not validated. It has the same
  domain-judgment caveat as every other pathogen's weights.
- The arcpy export step, `export_site_layers.py` under ArcGIS Pro's Python, is
  not run as part of this contract. It needs the user to create and populate the
  `Anthracnose` feature class first. It also runs outside the plain `.venv` that this assistant works in.

## Definition of done
- This contract exists (done).
- Code changes in `pathogens.py`, `export_site_layers.py`,
  `run_real_site_risk_raster.py`, and `fetch_wind_rose.py` are done. They were
  verified not to break the existing two sites (done).
- Full run against real `Anthracnose` data: done (2026-09-04).

## Verification (2026-09-04)
- Code changes were made. `run_real_site_risk_raster.py` was re-run before the
  real `Anthracnose` data existed. `red_ring_rot` and `phytophthora` still
  processed the same as before, with the same risk ranges. Then the run failed
  with a clear `FileNotFoundError` on `data/site_anthracnose/grid_meta.json`.
  That was expected. It confirmed the new `RUNS` entry does not disturb the two working sites.
- **Full pipeline run, after the feature class was created:**
  1. The user created and populated `Anthracnose` in `PathogenProject.gdb`. It
     is a point feature class with the same schema as `RedRingRot` and
     `Phytophthora`. It has 2 confirmed cases.
  2. `export_site_layers.py` ran under ArcGIS Pro's Python. All three
     `CASE_LAYERS` entries exported cleanly in one run. `RedRingRot`,
     `Phytophthora`, and `Anthracnose` were all re-exported together. `main()`
     loops over the whole dict, so this is expected. It is not specific to anthracnose.
     `Anthracnose` produced a 200x200 grid at 10 m, with 2 known cases, in
     `data/site_anthracnose`.
  3. `fetch_wind_rose.py` (plain `.venv`). The nearest usable station for
     `site_anthracnose` is `EUG`, at 13.6 km with 597203 obs. It is the same station
     the `phytophthora` site uses. Prevailing direction is 224.7 deg. Directionality strength is 0.156.
  4. `run_real_site_risk_raster.py` (plain `.venv`). The `anthracnose` risk
     raster is 200x200 cells. Its range is 0.000-0.229, its mean is 0.001, and it has 2 source cases.
     The preview (`outputs/anthracnose_site_risk_preview.png`) shows a plausible
     footprint around both known cases. It is stretched slightly toward the
     northeast. That is the downwind direction for `EUG`'s prevailing 224.7 deg.
     The directional effect is smaller than `red_ring_rot`'s. This fits `EUG`'s
     lower directionality strength (0.156, against 0.428 for `red_ring_rot`).
  5. Regression. `red_ring_rot` (range 0.000-0.405) and `phytophthora` (range
     0.000-0.079) both came back with the same risk ranges as before the re-export. Re-exporting all three sites together did not change the two sites that already worked.
- The functional gap is closed. `compute_risk_raster` now runs for `anthracnose`
  against real site data with no `ValueError`. This matches how
  `phytophthora`'s gap was closed in `wind_dispersal_and_soil_reweight.md`.
- **Bug found and fixed after the run**: `import_risk_raster.py` is the arcpy
  step. It converts the engine's `.npy` output into a georeferenced GeoTIFF for
  `PathogenProject.aprx`. It keeps its own hardcoded `OUTPUT_BASENAMES` list,
  separate from `run_real_site_risk_raster.py`'s `RUNS`. This was missed when
  anthracnose was first wired in. Without a fix, `anthracnose_site_risk` would
  have been skipped silently, with no error. `"anthracnose_site_risk"` was added
  to that list. The script was re-run under ArcGIS Pro's Python. Now
  `outputs/anthracnose_site_risk.tif` is written, with `.tif.xml`, `.tif.aux.xml`,
  and `.tfw`. This matches the output set of the other two sites.
