# Feature contract: Red ring rot wind-dispersal realism

## Status
Implemented. Part A was done on 2026-08-09. Part B was done on 2026-09-04.
The verification sections below record the results.

## Problem
Two parts of the current `red_ring_rot` model do not match how
*Porodaedalea pini* spreads. The fungus releases airborne basidiospores.
Wind carries them. It infects mainly through wounds and broken tops.

1. **`spatial_weights` gives weight to `soil` (0.25), and `environmental_triggers`
   gives weight to `moisture_weight` (0.5).** This weighting fits a soil-borne
   pathogen like `phytophthora` (see `pathogens.py`). This config was apparently
   patterned after that pathogen. Soil drainage and moisture are at best a weak,
   indirect signal for this fungus. They may track site wetness or tree stress.
   They are not a direct transmission route, as they are for a root or collar-rot pathogen.
2. **`spread_engine.py`'s dispersal kernel is radially symmetric.**
   `_distance_matrix` and `_dispersal_kernel` score only by Euclidean distance.
   Wind-dispersed spores should show a directional bias. Risk should be higher
   downwind of a source and lower upwind. The engine does not represent this, for any pathogen.

The second gap mirrors the first. **`phytophthora` has no `spatial_weights`
entry.** It has only `environmental_triggers`. `phytophthora` spreads through soil
and root contact (`transmission_mode: "soil"`, `moisture_weight: 0.9`). So the
soil-heavy weighting that does not fit `red_ring_rot` is the right shape for
`phytophthora`. It is missing. In practice, `compute_risk_raster` needs at least one
`spatial_weights` surface in the environment grid to set the output shape. With
`spatial_weights` missing, `phytophthora` cannot run against the real-site raster
pipeline at all. This is a functional gap, not only a modeling-accuracy gap.

## Goal
Move the soil and moisture weighting off `red_ring_rot`, where it does not fit
the wind and wound transmission biology. Move it onto `phytophthora`, where it
does fit. Then each config's weighting matches its own `transmission_mode`. It
should not be copied from one config to the other. Also define what directional
wind dispersal needs, once real wind data exists.

## Scope

### Part A: config re-weight (no new data required, feasible now)
- Reduce or drop `soil` from `red_ring_rot["spatial_weights"]`. If it stays,
  document it as a weak stress or wetness proxy, not a transmission route. That keeps the reasoning from being lost.
- Review `moisture_weight` in `environmental_triggers` the same way. Check
  whether it carries weight it has not earned for this pathogen's infection
  biology. Separate that from the fungus's growth conditions once it is established in a tree.
- Give more emphasis to `land_cover` (stand density and host presence, already available)
  and `terrain` (slope and aspect). `terrain` is currently the closest available
  proxy for wind exposure. See `spatial_inputs.score_terrain`.
- Add a `spatial_weights` block to `phytophthora`, weighted toward `soil` and
  `terrain` (low-lying, poorly drained ground). This mirrors the emphasis
  `red_ring_rot` loses. It fits a root or collar-rot pathogen's transmission
  mode. It also fixes the gap that stops `phytophthora` from running against the
  real-site raster pipeline.
- Add a comment in `pathogens.py` next to both `red_ring_rot` and
  `phytophthora`. Ideally, also add general guidance in the module docstring.
  The comment should say that `spatial_weights` must be reasoned through for each
  pathogen's actual transmission mode. Do not copy them from a similar-looking config.

### Part B: directional dispersal kernel (implemented 2026-09-04)
- `_dispersal_kernel` is now direction-aware. A new helper, `_bearing_matrix`,
  gives the compass bearing from source to target. When a `wind` dict is given,
  the decay rate for each source and target pair is scaled by
  `1 - directionality_strength * cos(bearing - downwind_direction)`. Downwind
  targets decay more slowly, so they reach farther. Upwind targets decay faster
  than the isotropic `exp(-decay_rate * distance)` baseline.
  `downwind_direction = prevailing_direction_deg + 180`. IEM's wind rose
  convention is "direction the wind blows FROM," so the downwind direction is the opposite bearing.
- **Deviation from the original contract shape.** The contract first proposed a
  `wind_bias` dict stored per pathogen in `pathogens.py`. The implementation does not do this.
  Wind direction and strength are loaded per *site*, from that site's
  `wind_rose.json`. `run_real_site_risk_raster.py` loads them. They are passed to
  `compute_risk` and `compute_risk_raster` as an engine-level `wind` argument.
  Prevailing wind is a property of the site's nearest station, not of the
  pathogen. So it does not belong on the pathogen config. The gate the contract
  asked for is kept. The wind is used only when `transmission_mode` is `"vector"`
  or `"airborne"`, and wind data is available. The engine functions
  (`compute_risk` and `compute_risk_raster`) check `pathogen_config["transmission_mode"]`
  before they use a passed-in `wind`. The check does not live on the config dict.
- This was unblocked by the real wind data (see `docs/feature_contracts/real_wind_data.md`).
  `PathogenPy/fetch_wind_rose.py` now produces `data/<site>/wind_rose.json` for each site.

## Inputs
- Part A: the existing `pathogens.py` config only.
- Part B: `data/<site>/wind_rose.json` (prevailing direction and directionality
  strength). `PathogenPy/fetch_wind_rose.py` produces it from IEM's public API.
  See `docs/feature_contracts/real_wind_data.md`.

## Outputs
- Part A: updated `red_ring_rot` and `phytophthora` configs. Each config's
  spatial weighting matches its own transmission biology. The reasoning is
  documented inline, so it does not regress. `phytophthora` can now run against the real-site raster pipeline.
- Part B: an anisotropic dispersal kernel option in `spread_engine.py`. It is
  opt-in for each call, through an engine-level `wind` argument. It is not a
  pathogen config field (see the deviation note above). It is gated by
  `transmission_mode`. `run_real_site_risk_raster.py` adds each site's
  `wind_rose.json` automatically, when the file exists.

## Success criteria
- Part A: the weights for `red_ring_rot` and `phytophthora` are defensible on a
  read-through. A reviewer can see why each surface has its weight for that
  pathogen. The numbers alone are not enough. `compute_risk_raster` runs for
  `phytophthora` against `data/site/` with no `ValueError`.
- Part B: re-running the real-site risk raster with a known prevailing wind
  direction gives a visibly elongated downwind lobe. The old result was a
  symmetric ring. This is confirmed in the Part B verification below.

## Non-goals
- Neither reweighted config is **validated**. Both are still domain-judgment
  prototypes. The same caveat applies to the soil-drainage and slope/aspect scores they adjust.
  The anisotropic kernel's shape is also unvalidated. It uses a cosine-blended
  decay rate. It is a defensible, explainable first pass. It is not fit to real spore-dispersal data.
- This does not change the configs for `anthracnose` or `emerald_ash_borer`.
  They deserve the same review later. That work is out of scope here. Neither
  pathogen currently runs against a real site raster. So the wind kernel is untested for them. The engine gate (`transmission_mode`) would still allow it.
- No seasonal wind split. See the bimodal-wind caveat in the Part B verification
  below and in `docs/notes/real_wind_data.md`.

## Definition of done
- This contract exists (done).
- Part A implemented and verified (done, 2026-08-09).
- Part B implemented and verified (done, 2026-09-04).

## Verification (Part A, 2026-08-09)
- `red_ring_rot`: `soil` was removed from `spatial_weights` entirely.
  `moisture_weight` in `environmental_triggers` went from 0.5 to 0.2. Its
  `spatial_weights` share stayed at 0.15. Its overall role is smaller now,
  because `land_cover` (0.45) and `terrain` (0.35) dominate.
  The removed `soil` weight did not move to `moisture`. It is kept small and
  framed as a spore-germination factor. It was not reassigned as a whole.
- `phytophthora`: the missing `spatial_weights` block was added. `soil` 0.55,
  `terrain` 0.25, `land_cover` 0.2.
- Regression: `run_prototype.py` and `run_red_ring_rot_grove.py` both still run
  cleanly. `phytophthora`'s synthetic-environment output is unchanged. That
  environment has only `moisture` and `temp` surfaces. So it still uses the
  `environmental_triggers` fallback path, which this change did not touch.
  `red_ring_rot`'s numbers shifted slightly, as expected.
- The specific functional gap is confirmed closed. `compute_risk_raster` now
  runs for `phytophthora` against `data/site/` (67x67 raster, no `ValueError`).
  The first test run used the existing `RedRingRot` known case. It only exercised the code path.
- **Update 2026-08-09**: a real `Phytophthora` feature class now exists in
  `PathogenProject.gdb`. It has one confirmed case: `ChLa`, Port Orford cedar.
  This is a strong real-world match. *Phytophthora lateralis* is the Port Orford cedar root-rot pathogen in Oregon.
  `export_site_layers.py` and `run_real_site_risk_raster.py` were generalized. They
  now export and compute for each known-case feature class. `RedRingRot` uses
  `data/site/`. `Phytophthora` uses `data/site_phytophthora/`. Before, one case was hardcoded.
  The end-to-end run on the real case gave a risk range of 0.000-0.130. The
  risk is flat except at the source cell. This is expected, not a bug. `phytophthora`'s
  `max_dispersal_distance_m` (25 m) is smaller than the 30 m grid cell size. So
  the dispersal kernel is already near zero one cell from the source.
  **The current 30 m raster resolution is too coarse to show `phytophthora`'s
  short-range spread.** A finer grid (5-10 m) would be needed to see a useful
  pattern for this pathogen. `ChLa` is also still missing from
  `phytophthora["host_susceptibility"]`. This does not block raster mode, which
  does not use that field. It is needed before any point-based scoring.

## Verification (Part B, 2026-09-04)
- `run_real_site_risk_raster.py` runs cleanly end to end for both sites, with the new `wind` wiring.
- `red_ring_rot` (`data/site`, station `77S`: prevailing 270.7 deg,
  directionality strength 0.428). The raster was compared with `wind=None`
  and with `wind={prevailing_direction_deg: 270.7, directionality_strength: 0.428}`.
  The two rasters differ (`np.allclose` is false). Sampling the source cell's row:
  14 cells downwind (east, since wind blows *from* the west) the risk score is 0.0179.
  14 cells upwind (west) it is 0.00086. That is about a 20x asymmetry. The
  regenerated preview PNG (`outputs/red_ring_rot_site_risk_preview.png`) shows
  the risk lobe stretched toward higher x (east) of the known-case marker. The old result was a symmetric ring. This meets the success criterion.
- `phytophthora` (soil-borne, `transmission_mode: "soil"`): the raster is
  **bit-identical** (`np.array_equal` is true) with or without `wind`. This
  confirms the `transmission_mode` gate in `compute_risk` and `compute_risk_raster` works. The
  change has no effect on non-wind-dispersed pathogens. `run_real_site_risk_raster.py`
  still loads and passes `wind_rose.json` for every site, with no check.
- Regression: `run_prototype.py` and `run_red_ring_rot_grove.py` both call
  `compute_risk` without the new `wind` argument. Both still run to completion
  with no errors. The default `wind=None` keeps the prior behavior exactly. No output change was expected or seen.
- **Caveat carried over from `docs/notes/real_wind_data.md`**: both sites are in
  the Willamette Valley. The valley has a documented bimodal seasonal wind
  pattern. Winter is more southerly. Summer is more northerly. The `wind_rose.json`
  values here are one all-season circular mean. That mean partly cancels the bimodality. So
  `directionality_strength` is a weaker confidence signal than it looks. This is especially true where the
  seasonal components oppose each other more evenly. For `red_ring_rot`'s station (`77S`,
  strength 0.428, a fairly strong single-direction signal) this was not a live
  concern. It would matter more before using this kernel for a pathogen and site
  near a station with a low `directionality_strength`. An example is `EUG`'s 0.156.
  No seasonal split was built in this pass. See this contract's Non-goals.
