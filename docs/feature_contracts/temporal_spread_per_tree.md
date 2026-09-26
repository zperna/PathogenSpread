# Feature contract: temporal spread simulation on the per-tree POS inventory

## Problem
`spread_engine.compute_risk` is single-step. Every susceptible tree is
scored against the *current* known cases only. A tree beyond
`max_dispersal_distance_m` of every known case scores 0, even when a
dense chain of susceptible hosts connects it to a case.

The POS integration (`docs/feature_contracts/site_tree_host_inventory.md`)
just added 1,084-2,330 real host trees per site -- a host network an
infection front could walk along -- but nothing in the engine represents
that walk. The single-step run showed the limit directly: `phytophthora`
returned an all-zero ranking because its one nearby host sits 84.6 m past
its 25 m dispersal cap, with no way to model a multi-hop path.

## Goal
Add a discrete-generation simulation that iterates the existing per-tree
infection math with a growing infected set, so the output is a spread
trajectory over N generations across the real POS host network. Framed
explicitly as a what-if scenario, not a dated or validated forecast.

## Relationship to existing contracts
- Builds directly on `docs/feature_contracts/site_tree_host_inventory.md`
  (the POS inventory and the `compute_risk` per-tree path).
- Concrete per-tree realization of
  `docs/feature_contracts/temporal_spread_iteration.md`, which stays
  contract-only and raster-oriented. That older contract's "no
  directional spread" non-goal is now stale: the wind-aware dispersal
  kernel (`docs/feature_contracts/wind_dispersal_and_soil_reweight.md`
  Part B) is wired into `compute_risk`, and this simulation inherits it
  unchanged.

## Scope
1. **Helper refactor in `spread_engine.py`.** Extract the per-step
   hazard core from `compute_risk` into a private helper that takes the
   current source set and the current susceptible set and returns the
   0-1 score array (dispersal kernel x susceptibility x
   environmental_match x stress_amplification). `compute_risk`'s public
   signature and output stay identical -- it becomes a single call to
   the helper. Non-negotiable: verified by diffing every existing runner
   before/after.
2. **New module `spread_simulation.py`.**
   - `simulate_spread(inventory, pathogen_config, environment=None,
     wind=None, n_steps=None, seed=None)` -> DataFrame.
   - Returns the inventory plus:
     - `infected_at_step` -- 0 for the initial known cases, `t` for a
       tree promoted in generation `t`, NA if never promoted within the
       run.
     - `risk_at_infection` -- the hazard score in the generation the
       tree crossed threshold; NA if never.
   - Also returns a per-generation log: for each `t`, the list of newly
     infected `tree_id`s and the cumulative infected count, so any
     generation's promotions are reconstructable from the previous
     generation's infected set plus the threshold.
   - Loop, `t = 1 .. n_steps`:
     1. sources = trees with `infected == True`,
     2. hazard = helper(sources, still-susceptible trees),
     3. promote every tree with `hazard >= promotion_threshold`,
        flip its `infected` to True, tag `infected_at_step = t` and
        `risk_at_infection`,
     4. stop early if a generation promotes nothing (front stalled).
3. **`pathogens.py`: add a `spread_step` block per real-site pathogen.**
   `{"promotion_threshold": <0-1>, "step_label": "generation"}`. Reason
   the threshold per pathogen against its own single-step hazard
   magnitudes (see Open questions), the same discipline as
   `spatial_weights` -- do not copy one pathogen's value to another.
   `red_ring_rot`, `phytophthora`, `anthracnose` only;
   `emerald_ash_borer` stays out.
4. **New runner `run_real_site_tree_spread.py`** (plain `.venv`).
   - `RUNS` mirrors `run_real_site_tree_risk.py`.
   - Per run: `build_host_inventory`, `load_site_grid`, load
     `wind_rose.json`, `simulate_spread(...)`, then write:
     - `outputs/<pathogen>_site_tree_spread.csv` -- inventory +
       `infected_at_step` + `risk_at_infection`, sorted by
       `infected_at_step`.
     - `outputs/<pathogen>_site_tree_spread_curve.png` -- cumulative
       infected count per generation.
     - `outputs/<pathogen>_site_tree_spread_frames.png` -- small-
       multiples map, one panel per generation (or every k-th), infected
       trees colored by `infected_at_step`, original cases marked.
   - The runner prints `promotion_threshold` and `n_steps` prominently
     and every output artifact is labeled with them and with the
     "illustrative what-if, not a forecast" caveat.

## Inputs
- Per-site host inventory from `build_host_inventory`
  (`site_tree_host_inventory.md`).
- `load_site_grid` environment + `data/<site>/wind_rose.json`, same load
  as `run_real_site_tree_risk.py`.
- `pathogens.PATHOGENS[...]` with the new `spread_step` block.
- Run parameters: `n_steps` (or run-until-stalled with a cap -- Open
  questions), `seed` (only if stochastic mode is added).

## Outputs
- `PathogenPy/spread_simulation.py`,
  `PathogenPy/run_real_site_tree_spread.py`.
- `spread_step` blocks in `pathogens.py` for the three real-site
  pathogens.
- Per pathogen: spread CSV, epidemic-curve PNG, per-generation frames
  PNG.
- This contract, a design note, a verification note.

## Success criteria
1. Running N generations against a real site produces a spreading
   infected set that is neither static nor saturating the whole AOI, and
   whose growth is distance-bounded: the generation-`t` infected set
   lies within `t * max_dispersal_distance_m` of an original known case.
2. Each generation's newly infected trees are listed and reconstructable
   from the prior infected set plus the threshold -- no black box.
3. `anthracnose` shows a downwind-biased front: over N generations the
   mean bearing of infected trees from the nearest original case leans
   toward the site's downwind direction, more clearly than the single-
   step ranking did in `site_tree_host_inventory.md` (directionality
   compounds across generations).
4. `phytophthora` produces zero or near-zero spread at its threshold,
   consistent with the 84.6 m nearest-host / 25 m dispersal-cap gap
   already recorded for it.
5. `compute_risk` single-step output is unchanged after the helper
   refactor: `run_real_site_tree_risk.py`, `run_prototype.py`,
   `run_red_ring_rot_grove.py` all diff clean.
6. The raster path (`compute_risk_raster`,
   `run_real_site_risk_raster.py`) and the arcpy steps are untouched.

## Non-goals
1. **No calibration.** `promotion_threshold`, `n_steps`, and the
   "generation" unit are scenario inputs. The output is an illustrative
   trajectory, not dated and not validated. Stated on every artifact.
2. No stochastic ensemble in v1 (Open question -- deterministic
   threshold only unless decided otherwise).
3. No infection latency: a tree infected in generation `t` is an
   infectious source in generation `t + 1`.
4. No removal, mortality, or recovery state. Trees are susceptible or
   infected, monotonic -- an SI process, not SIR.
5. No new spread physics. Dispersal kernel, environmental match,
   susceptibility, stress, and the wind gate are exactly as
   `compute_risk` uses them now.
6. No seasonality and no per-generation environment change -- the
   environment grid is static across the whole run.
7. No human-assisted long jumps (firewood, nursery stock). Natural
   dispersal only, same as today.
8. `emerald_ash_borer` stays excluded -- no `spatial_weights`, no real
   site.
9. No raster temporal loop. `temporal_spread_iteration.md` remains
   contract-only for that path.

## Open questions (resolve in the design note)
1. **Deterministic vs stochastic promotion.** Deterministic threshold
   is recommended for v1: explainable, reproducible, matches the raster
   temporal contract. Stochastic (`P(infect) = 1 - exp(-hazard)`,
   seeded, K realizations, report per-tree infection frequency and
   median infection generation) -- later upgrade, or now?
2. **`promotion_threshold` per pathogen.** The single-step run peaked at
   hazard 0.214 for `red_ring_rot` and 0.086 for `anthracnose`. One
   shared default (say 0.10) would let `red_ring_rot` spread and nearly
   freeze `anthracnose`. The design note sets per-pathogen values and
   shows the single-step hazard distribution each is chosen against.
3. **`n_steps`.** Fixed default (e.g. 12) vs run-until-stalled with a
   hard cap. Recommendation: run-until-stalled, cap 25.
4. **Source handling between generations.** Confirm infected trees are
   dropped from the susceptible set each generation (never re-scored,
   never reinfected) and the `infected` boolean is the only state
   carried forward.
5. **Frame output format.** Small-multiples PNG vs animated GIF vs both.
   Recommendation: small-multiples PNG for v1 -- no new dependency,
   reviewable in a diff.
6. **`infected_at_step` for the initial cases.** 0 with an "initial
   case" flag and excluded from spread statistics, or NA.
   Recommendation: 0 + flag.

## Definition of done
1. This contract exists (done).
2. Design note resolves the six open questions (done,
   `docs/notes/temporal_spread_per_tree.md`).
3. Helper refactor done; `compute_risk` single-step output verified
   unchanged across all three existing runners (done, 2026-09-07).
4. `spread_simulation.py`, `run_real_site_tree_spread.py`, and the
   `spread_step` config blocks exist and run in the plain `.venv`
   (done).
5. All three real-site pathogens produce a spread CSV, an epidemic
   curve, and per-generation map frames (done).
6. Verification recorded below (done, 2026-09-07).

## Verification (2026-09-07)

### Regression (hard gate) -- PASS
- `_infection_hazard` extracted from `compute_risk`; the three
  `outputs/*_site_tree_risk.csv` are byte-identical before and after.
- `run_prototype.py` and `run_red_ring_rot_grove.py` run clean, printed
  tables unchanged.
- `run_real_site_risk_raster.py` re-run: risk ranges unchanged
  (0.000-0.405 / 0.000-0.079 / 0.000-0.229); no tracked `outputs/` file
  modified.

### Per-generation trajectory (threshold in parens, run-until-stalled)
- **red_ring_rot** (0.06): 1 initial case -> gen 1 +5 -> gen 2 +0,
  stalls. 5 trees infected over the run.
- **phytophthora** (0.05): 1 initial case -> gen 1 +0, stalls
  immediately. 0 trees. Correct null -- nearest host is 84.6 m, the
  dispersal cap is 25 m (matches `site_tree_host_inventory.md`).
- **anthracnose** (0.035): 2 initial cases -> +11, +7, +4, +3, +2, +0.
  6 generations, 27 trees infected, a clean rise-then-fall curve. This
  is the run that demonstrates a walking front.

### Distance bound -- PASS
Every tree with `infected_at_step == t` is within
`t * max_dispersal_distance_m` of an initial case, for both spreading
pathogens.

### Why red_ring_rot and anthracnose stall -- threshold-sensitive
Neither runs out of hosts in range. At the stall:
- red_ring_rot: 52 susceptible hosts within 150 m of an infected tree,
  best hazard 0.0512 vs threshold 0.06.
- anthracnose: 60 susceptible hosts within 200 m, best hazard 0.0318 vs
  threshold 0.035.
Both stop within ~15% of their threshold, so run length is sensitive to
it near these values -- exactly why the threshold is documented as a
knob to sweep, not a calibrated constant. Lowering red_ring_rot to
~0.05 sustains its front; the committed 0.06 is kept because it is the
defensible ~p70 value, not because it produces a longer demo.

### Downwind bias across generations -- partially met
Mean `|bearing - downwind|` for spread trees vs their nearest initial
case:
- red_ring_rot: 37 deg (single-step was ~100 deg). The front went
  downwind -- directionality compounds, as predicted. Small n (5).
- anthracnose: 87 deg (single-step was ~73 deg). No clearer lean. Its
  wind directionality strength is only 0.156, and the street-tree host
  geometry (roughly linear sycamore runs) drives the front's shape more
  than the weak wind bias does. Success criterion 3's prediction holds
  for the strongly-directional site, not the weakly-directional one.

### Explainability
The per-generation log lists every newly infected `tree_id`. A promoted
tree's infection is reconstructable from the prior generation's infected
set plus the threshold: `risk_at_infection` in the CSV is the hazard
value that cleared it.

### Follow-ups
- red_ring_rot barely spreads at this site (2 generations). The feature
  is demonstrated by anthracnose; the other two stall for documented
  reasons (no hosts in range / threshold just above the next ring).
- A threshold sweep per pathogen (e.g. 0.02-0.10 in steps) would show
  how trajectory length and extent respond -- a natural next what-if
  tool, not built here.
