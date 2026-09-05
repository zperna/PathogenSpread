# Design note: Wind-dispersal kernel (Part B)

Part A (spatial-weight reweighting) is covered by the earlier verification
in the contract itself; this note is Part B only -- the anisotropic
dispersal kernel, once real wind data existed.

## Approach
`spread_engine.py` previously scored dispersal purely by distance
(`_distance_matrix` + isotropic `exp(-decay_rate * distance)` in
`_dispersal_kernel`). Part B adds a direction-aware option without
changing that baseline when no wind data is supplied.

1. New `_bearing_matrix(sources_xy, targets_xy)`: same shape as
   `_distance_matrix` (n_targets x n_sources), compass bearing in degrees
   (0 = north, 90 = east, clockwise) from each source to each target. Uses
   `atan2(dx, dy)` -- swapped argument order from the usual math
   convention (`atan2(dy, dx)`) specifically to get compass bearings
   instead of standard mathematical angles, since that's the convention
   IEM's wind rose data (and `fetch_wind_rose.py`'s
   `circular_direction_and_strength`) already uses.
2. `_dispersal_kernel` gained optional `bearing_deg`/`wind_bias` params.
   When both are given: `downwind_deg = (prevailing_direction_deg + 180) %
   360` -- IEM directions are "where the wind blows FROM," so downwind
   (the direction spores actually travel) is the opposite bearing.
   `alignment = cos(bearing_deg - downwind_deg)` is 1.0 for a target
   directly downwind of a source, -1.0 directly upwind, 0 for crosswind.
   `effective_decay_rate = decay_rate * (1 - directionality_strength *
   alignment)` -- downwind targets (alignment near 1) get a reduced decay
   rate (slower falloff, farther reach); upwind targets (alignment near
   -1) get an increased decay rate (faster falloff, shorter reach);
   crosswind targets are close to the unmodified isotropic rate.
   `directionality_strength = 0` collapses this back to the exact
   isotropic kernel regardless of bearing -- there's no discontinuity
   between "wind data available but weak" and "no wind data."
3. `compute_risk` and `compute_risk_raster` both gained an optional
   `wind=None` parameter (a `{prevailing_direction_deg,
   directionality_strength}` dict). Each only computes `_bearing_matrix`
   and passes it through when `wind is not None` *and*
   `pathogen_config.get("transmission_mode") in ("airborne", "vector")` --
   the gating this contract's Part B originally asked for, just
   implemented as a runtime check in the engine rather than a static field
   on the config.
4. `run_real_site_risk_raster.py` loads `data/<site>/wind_rose.json` (if
   present) per site and passes the two fields `compute_risk_raster` needs
   as `wind`. It does this unconditionally for every site/pathogen pair in
   `RUNS` -- the transmission_mode gate inside the engine is what actually
   decides whether it's used, so this file doesn't need its own
   per-pathogen branching.

## Why not a per-pathogen `wind_bias` config field
The contract's original Part B sketch proposed storing
`prevailing_direction_deg`/`directionality_strength` directly on each
pathogen's dict in `pathogens.py`. That stopped making sense once the
actual data source turned out to be a *site's* nearest weather station
(`fetch_wind_rose.py` looks up a station from `grid_meta.json`'s
centroid) -- the same pathogen run against two different sites would have
two different prevailing winds, so the number can't correctly live on a
pathogen-level config dict shared across sites. Keeping it as a
call-time argument, gated by the pathogen's `transmission_mode`, gets the
same "pathogen biology decides whether wind applies" behavior the
contract wanted, without a config field that would only ever be correct
for one site at a time.

## Assumptions
- Cosine-blended decay rate (rather than, say, an elliptical kernel or a
  von Mises-weighted distance) is a deliberately simple, explainable first
  pass, consistent with this whole engine's stated design principle --
  not fit against any real spore-dispersal or disease-spread-rate data.
- Uses the wind rose's single all-season circular mean as-is. Both current
  sites sit in the Willamette Valley, which has a documented winter/summer
  bimodal wind pattern (see `docs/notes/real_wind_data.md`) that an
  all-season mean partially cancels out. This means
  `directionality_strength` understates how directional the wind actually
  is in any *given season* -- treated here as an accepted simplification
  for a prototype, not silently ignored, but a seasonal split (e.g.
  separate wind roses per season, blended by which season a scenario is
  modeling) would be a more faithful next step before leaning on this for
  anything beyond illustrative risk mapping.
- No new dependency: `_bearing_matrix` is plain NumPy, same style as
  `_distance_matrix` next to it.

## Verification
See "Verification (Part B, 2026-09-04)" in
`docs/feature_contracts/wind_dispersal_and_soil_reweight.md` for the full
numeric results (downwind/upwind asymmetry, `transmission_mode` gating
confirmed as a true no-op for `phytophthora`, and regression checks
against `run_prototype.py`/`run_red_ring_rot_grove.py`). Summary: the
kernel change is real (rasters differ with vs. without wind), correctly
directional (downwind risk reaches farther than upwind, ~20x at 14 cells
out for `red_ring_rot`), correctly gated (zero effect on a soil-borne
pathogen even when wind data is passed in), and non-breaking (every
existing call site that doesn't pass `wind` behaves exactly as before).

## Update summary
- `spread_engine.py`: `_bearing_matrix` added; `_dispersal_kernel`,
  `compute_risk`, `compute_risk_raster` extended with optional
  `bearing_deg`/`wind_bias`/`wind` params, gated by `transmission_mode`.
- `run_real_site_risk_raster.py`: loads each site's `wind_rose.json` (when
  present) and passes it through to `compute_risk_raster`.
- `pathogens.py`: unchanged -- no `wind_bias` field added, per the
  deviation explained above.
- Contract's Part B section, Success criteria, Non-goals, and Definition
  of done all updated to reflect completion; this note added as its
  companion design note.
- Remaining for next iteration: the seasonal-bimodal-wind caveat above is
  still unaddressed (no seasonal wind roses exist yet); `anthracnose` and
  `emerald_ash_borer` don't currently run against any real site raster, so
  this kernel is unexercised for them even though both are wind/vector
  transmission modes the engine gate would allow.
