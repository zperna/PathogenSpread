# Design note: Wind-dispersal kernel (Part B)

Part A (spatial-weight reweighting) is covered by the verification in the
contract itself. This note covers Part B only. Part B is the anisotropic
dispersal kernel. It was built once real wind data existed.

## Approach
`spread_engine.py` used to score dispersal by distance alone. It used
`_distance_matrix` and an isotropic `exp(-decay_rate * distance)` in
`_dispersal_kernel`. Part B adds a direction-aware option. When no wind data
is given, the baseline does not change.

1. New `_bearing_matrix(sources_xy, targets_xy)`. It has the same shape as
   `_distance_matrix` (n_targets x n_sources). It gives the compass bearing in
   degrees from each source to each target. 0 is north, 90 is east, and the angle
   increases clockwise. It uses `atan2(dx, dy)`. The argument order is swapped from the usual
   math convention (`atan2(dy, dx)`). This gives compass bearings, not standard
   math angles. IEM's wind rose data and `fetch_wind_rose.py`'s
   `circular_direction_and_strength` both use the compass convention.
2. `_dispersal_kernel` gained two optional parameters, `bearing_deg` and
   `wind_bias`. When both are given:
   - `downwind_deg = (prevailing_direction_deg + 180) % 360`. IEM directions
     give where the wind blows *from*. The direction spores travel is the opposite bearing.
   - `alignment = cos(bearing_deg - downwind_deg)`. It is 1.0 for a target
     directly downwind of a source. It is -1.0 directly upwind. It is 0 for crosswind.
   - `effective_decay_rate = decay_rate * (1 - directionality_strength * alignment)`.
     Downwind targets (alignment near 1) get a lower decay rate. The falloff is slower and the reach is farther.
     Upwind targets (alignment near -1) get a higher decay rate. The falloff is faster and the reach is shorter.
     Crosswind targets stay close to the unmodified isotropic rate.
   - `directionality_strength = 0` returns the exact isotropic kernel, for any
     bearing. There is no jump between "wind data present but weak" and "no wind data."
3. `compute_risk` and `compute_risk_raster` each gained an optional `wind=None`
   parameter. It is a `{prevailing_direction_deg, directionality_strength}` dict.
   Each one calls `_bearing_matrix` and passes the result on only when
   `wind is not None` *and*
   `pathogen_config.get("transmission_mode") in ("airborne", "vector")`.
   The original contract asked for this gate. It is
   now a runtime check in the engine, not a static field on the config.
4. `run_real_site_risk_raster.py` loads `data/<site>/wind_rose.json` for each
   site, if the file exists. It passes the two fields that `compute_risk_raster`
   needs as `wind`. It does this for every site and pathogen pair in `RUNS`. It has no per-pathogen branching. The
   `transmission_mode` gate inside the engine decides whether the wind is used.

## Why not a per-pathogen `wind_bias` config field
The contract's original Part B sketch stored `prevailing_direction_deg` and
`directionality_strength` directly on each pathogen's dict in `pathogens.py`.
That stopped making sense. The real data source is the nearest weather station
for each *site*. `fetch_wind_rose.py` finds that station from the centroid in
`grid_meta.json`. The same pathogen run at two sites would have two different
prevailing winds. A pathogen-level config dict is shared across sites, so the number cannot live there correctly.
A call-time argument, gated by the pathogen's `transmission_mode`, gives the behavior the contract wanted. Pathogen biology decides whether
wind applies. It avoids a config field that would be correct for only one site at a time.

## Assumptions
- The cosine-blended decay rate is a deliberately simple first pass. It was
  chosen over an elliptical kernel or a von Mises-weighted distance. It fits
  the engine's stated design principle of simple, explainable math. It was not
  fit against any real spore-dispersal or disease-spread data.
- The kernel uses the wind rose's single all-season circular mean as is. Both
  current sites are in the Willamette Valley. The valley has a documented winter
  and summer bimodal wind pattern (see `docs/notes/real_wind_data.md`). An
  all-season mean partly cancels that pattern. So `directionality_strength`
  understates how directional the wind is in any given season. This is accepted
  as a simplification for a prototype. It is not ignored. A seasonal split would be a more faithful next step. For example, separate wind roses per season,
  blended by the season a scenario models. That step should come before the kernel is used for more than illustrative risk maps.
- No new dependency. `_bearing_matrix` uses plain NumPy, in the same style as
  `_distance_matrix` next to it.

## Verification
The full numeric results are in "Verification (Part B, 2026-09-04)" in
`docs/feature_contracts/wind_dispersal_and_soil_reweight.md`. The
downwind and upwind asymmetry is there. So is the `transmission_mode` gate, confirmed as a true no-op
for `phytophthora`. The regression checks against `run_prototype.py` and `run_red_ring_rot_grove.py` are there too.
In short:
- The kernel change is real. Rasters differ with and without wind.
- It is directional. Downwind risk reaches farther than upwind risk. For
  `red_ring_rot`, the ratio is about 20x at 14 cells out.
- It is gated correctly. It has zero effect on a soil-borne pathogen, even when wind data is passed in.
- It does not break anything. Every existing call that does not pass `wind` behaves as before.

## Update summary
- `spread_engine.py`: added `_bearing_matrix`. Extended `_dispersal_kernel`,
  `compute_risk`, and `compute_risk_raster` with optional `bearing_deg`,
  `wind_bias`, and `wind` parameters. The `transmission_mode` gate controls them.
- `run_real_site_risk_raster.py`: loads each site's `wind_rose.json` when it
  is present. It passes the data to `compute_risk_raster`.
- `pathogens.py`: unchanged. No `wind_bias` field was added, per the deviation explained above.
- The contract's Part B section, Success criteria, Non-goals, and Definition
  of done were all updated to show completion. This note was added as its companion design note.
- Remaining for the next iteration. The seasonal bimodal wind caveat above is
  still open. No seasonal wind roses exist yet. `anthracnose` and
  `emerald_ash_borer` do not run against any real site raster. So this kernel is
  untested for them. Both are wind or vector transmission modes, which the engine gate would allow.
