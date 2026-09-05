# Feature contract: Anthracnose real-site risk raster

## Problem
`anthracnose` has no `spatial_weights` block in `pathogens.py` -- same
functional gap `phytophthora` had before
`docs/feature_contracts/wind_dispersal_and_soil_reweight.md` fixed it.
`compute_risk_raster` requires at least one `spatial_weights` surface
present in the environment grid to determine the raster's shape, so
`anthracnose` cannot run against a real site raster at all today, only
against synthetic data via `compute_risk`.

Separately, the real-site pipeline (`export_site_layers.py` ->
`fetch_wind_rose.py` -> `run_real_site_risk_raster.py`) only knows about
two known-case feature classes (`RedRingRot`, `Phytophthora`). The user is
creating a third, `Anthracnose`, with real confirmed cases.

## Goal
Give `anthracnose` a `spatial_weights` block reasoned through its own
transmission biology (not copied from another pathogen), and wire a third
site (`data/site_anthracnose/`) through the existing real-site pipeline --
reusing all of it unchanged, the same way `Phytophthora` was added
alongside `RedRingRot`.

## Scope
- `pathogens.py`: add `anthracnose["spatial_weights"]`. Anthracnose is
  wind/rain-splash, canopy-to-canopy, short range (200m
  `max_dispersal_distance_m`), hosts are broadleaf (maple, oak, sycamore,
  dogwood) -- a different mechanism from `red_ring_rot`'s wind-driven
  wound infection (which the `exposure`/TPI surface targets) or
  `phytophthora`'s root contact. `land_cover` (host canopy density -- the
  medium spread has to move through) is the dominant driver; `wetness`
  (TWI, already used as a moisture-accumulation proxy for `phytophthora`)
  stands in for the "cool wet spring conditions" driver already in
  `environmental_triggers`, just a foliar-humidity reading instead of a
  root-zone one. `exposure`/`terrain`/`soil` are left out -- ridge wind
  exposure and soil drainage aren't defensible drivers for rain-splash
  canopy spread at this range.
- `export_site_layers.py`: add `"Anthracnose": "site_anthracnose"` to
  `CASE_LAYERS`. No other change -- the export function is already
  generalized per known-case feature class.
- `run_real_site_risk_raster.py`: add
  `("anthracnose", "site_anthracnose", "anthracnose_site_risk")` to `RUNS`.
- `fetch_wind_rose.py`: add `"site_anthracnose"` to `SITE_NAMES`.
  `anthracnose`'s `transmission_mode` is `"airborne"`, so once its
  `wind_rose.json` exists, `run_real_site_risk_raster.py` automatically
  feeds it into the wind-aware dispersal kernel (Part B of
  `wind_dispersal_and_soil_reweight.md`) -- no extra wiring needed, the
  engine's existing `transmission_mode` gate handles it.

## Inputs
- A new `Anthracnose` point feature class in `PathogenProject.gdb`, same
  schema as `RedRingRot`/`Phytophthora` (`tree_id`, `species`,
  `stress_index`, `infected`), created and populated by the user.
- Everything else (NLCD, gNATSGO, ODF DEM service, IEM wind API) is
  already wired and needs no site-specific changes.

## Outputs
- `data/site_anthracnose/` (grid + known cases), `outputs/
  anthracnose_site_risk.{npy,tif}` + preview, once exported.
- `anthracnose["spatial_weights"]` in `pathogens.py`.

## Success criteria
- `compute_risk_raster` runs for `anthracnose` against `data/
  site_anthracnose/` without a `ValueError` -- closes the same functional
  gap `phytophthora`'s missing block used to be.
- `red_ring_rot`/`phytophthora` outputs are unaffected (regression).
- Once wind data exists for the new site, the anthracnose raster shows the
  same kind of downwind-elongated lobe already verified for `red_ring_rot`.

## Non-goals
- Does not address `emerald_ash_borer`'s missing `spatial_weights` --
  no feature class or real cases exist for it yet.
- No claim `anthracnose["spatial_weights"]` is validated -- same
  domain-judgment caveat as every other pathogen's weights.
- The arcpy export step itself (`export_site_layers.py` under ArcGIS
  Pro's Python) is not run as part of this contract -- it depends on the
  user creating and populating the `Anthracnose` feature class first, and
  runs outside the plain `.venv` this assistant operates in.

## Definition of done
- This contract exists (done).
- Code changes (`pathogens.py`, `export_site_layers.py`,
  `run_real_site_risk_raster.py`, `fetch_wind_rose.py`) done and verified
  not to break the existing two sites (done).
- Full run against real `Anthracnose` data: done (done, 2026-09-04).

## Verification (2026-09-04)
- Code changes made; `run_real_site_risk_raster.py` re-run before the real
  `Anthracnose` data existed: `red_ring_rot` and `phytophthora` still
  processed identically (same risk ranges as before), then failed with a
  clear `FileNotFoundError` on `data/site_anthracnose/grid_meta.json` --
  expected, confirmed the new `RUNS` entry doesn't disturb the two working
  sites.
- **Full pipeline run, post feature-class creation:**
  1. User created and populated `Anthracnose` (point feature class, same
     schema as `RedRingRot`/`Phytophthora`) in `PathogenProject.gdb`, 2
     confirmed cases.
  2. `export_site_layers.py` run under ArcGIS Pro's Python -- all three
     `CASE_LAYERS` entries exported cleanly in one run (`RedRingRot`,
     `Phytophthora`, `Anthracnose` all re-exported together, since
     `main()` loops the whole dict -- expected, not anthracnose-specific).
     `Anthracnose`: 200x200 grid at 10m, 2 known cases, to
     `data/site_anthracnose`.
  3. `fetch_wind_rose.py` (plain `.venv`) -- `site_anthracnose`'s nearest
     usable station is `EUG` (13.6 km, 597203 obs), same station
     `phytophthora`'s site already uses: prevailing 224.7 deg,
     directionality strength 0.156.
  4. `run_real_site_risk_raster.py` (plain `.venv`) -- `anthracnose` risk
     raster: 200x200 cells, range 0.000-0.229, mean 0.001, 2 source cases.
     Preview (`outputs/anthracnose_site_risk_preview.png`) shows a
     plausible footprint around both known cases, modestly stretched
     toward the northeast (the downwind direction for `EUG`'s prevailing
     224.7 deg) -- a smaller directional effect than `red_ring_rot`'s,
     consistent with `EUG`'s lower directionality strength (0.156 vs.
     `red_ring_rot`'s 0.428).
  5. Regression: `red_ring_rot` (range 0.000-0.405) and `phytophthora`
     (range 0.000-0.079) both came back with the same risk ranges as
     before the re-export -- confirms re-exporting all three sites
     together didn't perturb the two already-working ones.
- Closes the functional gap: `compute_risk_raster` now runs for
  `anthracnose` against real site data without a `ValueError`, same as
  `phytophthora`'s gap closure in
  `wind_dispersal_and_soil_reweight.md`.
- **Bug found and fixed post-hoc**: `import_risk_raster.py` (the arcpy
  step that converts the engine's `.npy` output back into a georeferenced
  GeoTIFF for `PathogenProject.aprx`) keeps its own separate hardcoded
  `OUTPUT_BASENAMES` list, distinct from `run_real_site_risk_raster.py`'s
  `RUNS` -- missed when wiring anthracnose in originally, so it would have
  silently skipped `anthracnose_site_risk` with no error. Added
  `"anthracnose_site_risk"` to that list and re-ran under ArcGIS Pro's
  Python: `outputs/anthracnose_site_risk.tif` (+ `.tif.xml`/`.tif.aux.xml`/
  `.tfw`) now written, matching the other two sites' output set.
