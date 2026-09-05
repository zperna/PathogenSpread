# Feature contract: Red ring rot wind-dispersal realism

## Status
Contract only -- not yet implemented. Code is being left alone for now; this
documents the gap and the plan for closing it.

## Problem
Two parts of the current `red_ring_rot` model don't match how
*Porodaedalea pini* actually spreads (airborne basidiospores, wind-dispersed,
infecting primarily through wounds and broken tops):

1. **`spatial_weights` leans on `soil` (0.25) and `environmental_triggers`
   leans on `moisture_weight` (0.5)** -- weighting that fits a soil-borne
   pathogen like `phytophthora` (see `pathogens.py`), which this config was
   evidently patterned after. Soil drainage/moisture is at best a weak,
   indirect signal here (e.g. correlated with site wetness or tree stress),
   not a direct transmission pathway the way it is for a root/collar-rot
   pathogen.
2. **`spread_engine.py`'s dispersal kernel is radially symmetric**
   (`_distance_matrix` + `_dispersal_kernel` score purely by Euclidean
   distance). Wind-dispersed spores should show directional bias --
   elevated risk downwind of a source, reduced upwind -- and nothing in the
   engine represents that today, for any pathogen.

Separately, and the mirror image of point 1: **`phytophthora` has no
`spatial_weights` entry at all** -- only `environmental_triggers`. Since
`phytophthora` is genuinely soil/root-contact borne (`transmission_mode:
"soil"`, `moisture_weight: 0.9`), the soil-heavy weighting that doesn't
belong on `red_ring_rot` is actually the right shape for `phytophthora` --
it's just not there. Concretely, `compute_risk_raster` requires at least one
of a pathogen's `spatial_weights` surfaces to be present in the environment
grid to even determine the output shape; with `spatial_weights` missing
entirely, `phytophthora` cannot run against the real-site raster pipeline at
all today. This is a functional gap, not just a modeling-accuracy one.

## Goal
Move the soil/moisture-heavy spatial weighting off `red_ring_rot` (where it
doesn't fit the pathogen's wind/wound transmission biology) and onto
`phytophthora` (where it does), so each config's weighting matches its own
`transmission_mode` instead of one being copied onto the other. Also lay out
what directional wind dispersal would take to add once real wind data
exists.

## Scope

### Part A -- config re-weight (no new data required, feasible now)
- Reduce or drop `soil` from `red_ring_rot["spatial_weights"]`; if kept at
  all, document it explicitly as a weak stress/wetness proxy, not a
  transmission pathway, so the reasoning doesn't get silently lost.
- Re-examine `moisture_weight` in `environmental_triggers` the same way --
  check whether it's pulling weight it hasn't earned for this specific
  pathogen's infection biology, as distinct from the fungus's growth
  conditions once already established in a tree.
- Increase relative emphasis on `land_cover` (stand density / host
  presence -- already available) and `terrain` (slope/aspect, currently the
  closest available proxy for wind exposure -- see
  `spatial_inputs.score_terrain`).
- Add a `spatial_weights` block to `phytophthora`, weighted toward `soil`
  and `terrain` (low-lying/poorly-drained ground), mirroring the emphasis
  `red_ring_rot` is losing -- this is what actually fits a root/collar-rot
  pathogen's transmission mode, and it closes the gap where `phytophthora`
  currently can't run against the real-site raster pipeline at all.
- Add a comment in `pathogens.py` next to both `red_ring_rot` and
  `phytophthora` (and ideally as general guidance in the module docstring)
  warning that `spatial_weights` should be reasoned through per pathogen's
  actual transmission mode, not copied from a similar-looking config.

### Part B -- directional dispersal kernel (implemented 2026-09-04)
- Made `_dispersal_kernel` direction-aware via a new `_bearing_matrix`
  helper (compass bearing, source->target): when a `wind` dict is given,
  the per-source/target decay rate is scaled by
  `1 - directionality_strength * cos(bearing - downwind_direction)`, so
  downwind targets decay slower (reach farther) and upwind targets decay
  faster than the isotropic `exp(-decay_rate * distance)` baseline.
  `downwind_direction = prevailing_direction_deg + 180`, since IEM's wind
  rose convention is "direction wind blows FROM."
- **Deviation from this contract's original proposed shape**: rather than
  a `wind_bias` dict stored per pathogen in `pathogens.py`, wind direction/
  strength is loaded per *site* (from that site's `wind_rose.json`) in
  `run_real_site_risk_raster.py` and passed into `compute_risk`/
  `compute_risk_raster` as an engine-level `wind` argument. Prevailing wind
  is a property of the site's nearest station, not of the pathogen, so it
  doesn't belong on the pathogen config. The gating this contract asked
  for -- only apply when `transmission_mode` is `"vector"` or `"airborne"`
  and wind data is available -- is preserved; it just lives in the engine
  functions (`compute_risk`/`compute_risk_raster` check
  `pathogen_config["transmission_mode"]` before using a passed-in `wind`)
  instead of on the config dict.
- Unblocked by real wind data (see `docs/feature_contracts/real_wind_data.md`)
  -- `PathogenPy/fetch_wind_rose.py` now produces `data/<site>/wind_rose.json`
  per site.

## Inputs
- Part A: existing `pathogens.py` config only.
- Part B: `data/<site>/wind_rose.json` (prevailing direction, directionality
  strength), produced by `PathogenPy/fetch_wind_rose.py` from IEM's public
  API -- see `docs/feature_contracts/real_wind_data.md`.

## Outputs
- Part A: updated `red_ring_rot` and `phytophthora` configs whose spatial
  weighting each matches its own transmission biology, with the reasoning
  documented inline so it doesn't regress. `phytophthora` gains the
  ability to run against the real-site raster pipeline it currently can't.
- Part B: an anisotropic dispersal kernel option in `spread_engine.py`,
  opt-in per call via an engine-level `wind` argument (not a pathogen
  config field, see the deviation note above), gated by
  `transmission_mode`. `run_real_site_risk_raster.py` wires each site's
  `wind_rose.json` in automatically when present.

## Success criteria
- Part A: both `red_ring_rot`'s and `phytophthora`'s weights are defensible
  on a read-through -- someone reviewing the config can see *why* each
  surface is weighted the way it is for that specific pathogen, not just
  that the numbers exist. `compute_risk_raster` runs successfully for
  `phytophthora` against `data/site/` without a `ValueError`.
- Part B: re-running the real-site risk raster with a known prevailing
  wind direction produces a visibly elongated downwind lobe instead of the
  previous symmetric ring -- confirmed, see Part B verification below.

## Non-goals
- No claim that either reweighted config is *validated* -- both are still
  domain-judgment prototypes, same caveat as the current soil-drainage and
  slope/aspect scores they're adjusting. The same applies to the
  anisotropic kernel's shape (a cosine-blended decay rate) -- a defensible,
  explainable first pass, not a fit to real spore-dispersal data.
- This doesn't address `anthracnose` or `emerald_ash_borer`'s configs --
  worth the same scrutiny eventually, but out of scope here. Neither
  currently runs against a real site raster, so the wind kernel is untested
  for them even though the engine-level gating (`transmission_mode`) would
  technically allow it.
- No seasonal wind split -- see the bimodal-wind caveat in the Part B
  verification note below and `docs/notes/real_wind_data.md`.

## Definition of done
- This contract exists (done).
- Part A implemented and verified (done, 2026-08-09).
- Part B implemented and verified (done, 2026-09-04).

## Verification (Part A, 2026-08-09)
- `red_ring_rot`: dropped `soil` from `spatial_weights` entirely; cut
  `moisture_weight` in `environmental_triggers` from 0.5 to 0.2 and its
  `spatial_weights` share from 0.15 to 0.15 (unchanged share, smaller
  overall role now that `land_cover`/`terrain` dominate at 0.45/0.35).
  `soil`'s removed weight did not move onto `moisture` -- kept small and
  framed as a spore-germination factor, not reassigned wholesale.
- `phytophthora`: added the missing `spatial_weights` block (`soil` 0.55,
  `terrain` 0.25, `land_cover` 0.2).
- Regression: `run_prototype.py` and `run_red_ring_rot_grove.py` both still
  run cleanly; `phytophthora`'s synthetic-environment output is unchanged
  (that environment only has `moisture`/`temp` surfaces, so it still hits
  the `environmental_triggers` fallback path, untouched by this change);
  `red_ring_rot`'s numbers shifted slightly as expected.
- Confirmed the specific functional gap is closed: `compute_risk_raster`
  now runs for `phytophthora` against `data/site/` (67x67 raster, no
  `ValueError`). Initial test run used the existing `RedRingRot` known case
  purely to exercise the code path.
- **Update 2026-08-09**: a real `Phytophthora` feature class with one
  confirmed case (`ChLa` / Port Orford cedar -- a strong real-world match,
  since *Phytophthora lateralis* is specifically the Port Orford cedar
  root-rot pathogen in Oregon) now exists in `PathogenProject.gdb`.
  `export_site_layers.py` and `run_real_site_risk_raster.py` were
  generalized to export/compute per known-case feature class
  (`data/site/` for `RedRingRot`, `data/site_phytophthora/` for
  `Phytophthora`) instead of hardcoding one. Ran end to end against the
  real case: risk range 0.000-0.130, essentially flat except the source
  cell. That's expected, not a bug -- `phytophthora`'s
  `max_dispersal_distance_m` (25 m) is smaller than the 30 m grid cell
  size, so the dispersal kernel is already near zero one cell away from the
  source. **The current 30 m raster resolution is too coarse to usefully
  visualize phytophthora's short-range spread** -- a finer grid (5-10 m)
  would be needed to see a meaningful pattern for this pathogen
  specifically. `ChLa` is also still missing from
  `phytophthora["host_susceptibility"]` -- not a blocker for raster mode
  (which doesn't use it), but needed before any point-based scoring.

## Verification (Part B, 2026-09-04)
- `run_real_site_risk_raster.py` runs cleanly end to end for both sites
  with the new `wind` wiring in place.
- `red_ring_rot` (`data/site`, station `77S`: prevailing 270.7 deg,
  directionality strength 0.428): compared the raster with `wind=None`
  against `wind={prevailing_direction_deg: 270.7, directionality_strength:
  0.428}`. The two rasters are provably different (`np.allclose` false).
  Sampling the source cell's row: 14 cells downwind (east -- wind blows
  *from* the west, so downwind is east) the risk score is 0.0179; 14 cells
  upwind (west) it's 0.00086, a ~20x asymmetry. The regenerated preview PNG
  (`outputs/red_ring_rot_site_risk_preview.png`) visibly shows the risk
  lobe stretched toward higher x (east) of the known-case marker instead
  of the previous symmetric ring -- confirms the stated success criterion.
- `phytophthora` (soil-borne, `transmission_mode: "soil"`): raster is
  **bit-identical** (`np.array_equal` true) whether or not `wind` is
  passed in, confirming the `transmission_mode` gate in
  `compute_risk`/`compute_risk_raster` works and this change is a true
  no-op for non-wind-dispersed pathogens, even though `run_real_site_risk_
  raster.py` loads and passes `wind_rose.json` for every site
  unconditionally.
- Regression: `run_prototype.py` and `run_red_ring_rot_grove.py` (both call
  `compute_risk` without the new `wind` argument) still run to completion
  with no errors -- the default `wind=None` preserves prior behavior
  exactly, no output change expected or observed.
- **Caveat carried over from `docs/notes/real_wind_data.md`**: both sites
  sit in the Willamette Valley, which has a documented bimodal seasonal
  wind pattern (more southerly in winter, more northerly in summer). The
  `wind_rose.json` values used here are an all-season circular mean, which
  partially cancels that bimodality -- so `directionality_strength` is a
  weaker "confidence" signal than it looks, especially at a station where
  the seasonal components oppose more evenly. This wasn't a live concern
  for `red_ring_rot`'s station (`77S`, strength 0.428, a fairly strong
  single-direction signal) but would matter more before trusting this
  kernel for a pathogen/site combination sited near a station with a low
  `directionality_strength` (e.g. `EUG`'s 0.156) -- no seasonal split was
  built in this pass; see this contract's Non-goals.
