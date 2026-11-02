# Feature contract: temporal spread simulation on the per-tree POS inventory

## Problem
`spread_engine.compute_risk` is single-step. Every susceptible tree is scored against the *current* known cases only. A tree beyond `max_dispersal_distance_m` of every known case scores 0. This happens even when a dense chain of susceptible hosts connects it to a case.

The POS integration (`docs/feature_contracts/site_tree_host_inventory.md`) just added 1,084-2,330 real host trees per site. These trees form a host network that an infection front could move along. But nothing in the engine models that movement. The single-step run showed the limit directly. `phytophthora` returned an all-zero ranking. Its one nearby host sits 84.6 m past its 25 m dispersal cap. The engine has no way to model a multi-hop path.

## Goal
Add a discrete-generation simulation. It repeats the existing per-tree infection math with a growing infected set. The output is a spread trajectory over N generations across the real POS host network. The simulation is framed explicitly as a what-if scenario. It is not a dated or validated forecast.

## Relationship to existing contracts
- Builds directly on `docs/feature_contracts/site_tree_host_inventory.md` (the POS inventory and the `compute_risk` per-tree path).
- This is the per-tree version of `docs/feature_contracts/temporal_spread_iteration.md`, which stays contract-only and raster-oriented. That older contract's "no directional spread" non-goal is now stale. The wind-aware dispersal kernel (`docs/feature_contracts/wind_dispersal_and_soil_reweight.md` Part B) is wired into `compute_risk`. This simulation inherits it unchanged.

## Scope
1. **Helper refactor in `spread_engine.py`.** Extract the per-step hazard core from `compute_risk` into a private helper. The helper takes the current source set and the current susceptible set. It returns the 0-1 score array (dispersal kernel x susceptibility x environmental_match x stress_amplification). `compute_risk`'s public signature and output stay identical. After the change, `compute_risk` makes a single call to the helper. This is a hard requirement. Verify it by diffing every existing runner before and after the change.
2. **New module `spread_simulation.py`.**
   - `simulate_spread(inventory, pathogen_config, environment=None, wind=None, n_steps=None, seed=None)` -> `(df, log)` tuple. `df` is the per-tree DataFrame.
   - Returns the inventory plus:
     - `infected_at_step`: 0 for the initial known cases. `t` for a tree promoted in generation `t`. NA if never promoted within the run.
     - `risk_at_infection`: the hazard score in the generation the tree crossed the threshold. NA if never.
   - Also returns a per-generation log. For each `t`, the log lists the newly infected `tree_id`s and the cumulative infected count. Any generation's promotions can be rebuilt from the previous generation's infected set plus the threshold.
   - Loop, `t = 1 .. n_steps`:
     1. sources = trees with `infected == True`.
     2. hazard = helper(sources, still-susceptible trees).
     3. Promote every tree with `hazard >= promotion_threshold`. Flip its `infected` to True. Tag it with `infected_at_step = t` and `risk_at_infection`.
     4. Stop early if a generation promotes nothing. The front has stalled.
3. **`pathogens.py`: add a `spread_step` block per real-site pathogen.** The block is `{"promotion_threshold": <0-1>, "step_label": "generation"}`. Set the threshold for each pathogen against its own single-step hazard magnitudes (see Open questions). Use the same discipline as `spatial_weights`. Do not copy one pathogen's value to another. This applies to `red_ring_rot`, `phytophthora`, and `anthracnose` only. `emerald_ash_borer` stays out.
4. **New runner `run_real_site_tree_spread.py`** (plain `.venv`).
   - `RUNS` mirrors `run_real_site_tree_risk.py`.
   - Per run:
     1. `build_host_inventory`.
     2. `load_site_grid`.
     3. Load `wind_rose.json`.
     4. `simulate_spread(...)`.
     5. Write the outputs below.
   - Outputs:
     - `outputs/<pathogen>_site_tree_spread.csv`: inventory plus `infected_at_step` and `risk_at_infection`, sorted by `infected_at_step`.
     - `outputs/<pathogen>_site_tree_spread_curve.png`: cumulative infected count per generation.
     - `outputs/<pathogen>_site_tree_spread_frames.png`: small-multiples map. It has one panel per generation (or every k-th generation). Infected trees are colored by `infected_at_step`. Original cases are marked.
   - The runner prints `promotion_threshold` and `n_steps` prominently. Every output artifact is labeled with them and with the "illustrative what-if, not a forecast" caveat.

## Inputs
- Per-site host inventory from `build_host_inventory` (`site_tree_host_inventory.md`).
- `load_site_grid` environment and `data/<site>/wind_rose.json`. This is the same load as `run_real_site_tree_risk.py`.
- `pathogens.PATHOGENS[...]` with the new `spread_step` block.
- Run parameters: `n_steps`, or run until stalled with a cap (see Open questions). Also `seed`, but only if a stochastic mode is added.

## Outputs
- `PathogenPy/spread_simulation.py` and `PathogenPy/run_real_site_tree_spread.py`.
- `spread_step` blocks in `pathogens.py` for the three real-site pathogens.
- Per pathogen: a spread CSV, an epidemic-curve PNG, and a per-generation frames PNG.
- This contract, a design note, and a verification note.

## Success criteria
1. Running N generations against a real site produces a spreading infected set. It must not stay static. It must not saturate the whole AOI. Its growth is bounded by distance. The generation-`t` infected set lies within `t * max_dispersal_distance_m` of an original known case.
2. Each generation's newly infected trees are listed. They can be rebuilt from the prior infected set plus the threshold. There is no black box.
3. `anthracnose` shows a front biased downwind. Over N generations, the mean bearing of infected trees from the nearest original case moves toward the site's downwind direction. The effect is clearer than the single-step ranking in `site_tree_host_inventory.md`. Directionality compounds across generations.
4. `phytophthora` produces zero or near-zero spread at its threshold. This matches the 84.6 m nearest-host and 25 m dispersal-cap gap already recorded for it.
5. The single-step output of `compute_risk` is unchanged after the helper refactor. `run_real_site_tree_risk.py`, `run_prototype.py`, and `run_red_ring_rot_grove.py` all diff clean.
6. The raster path (`compute_risk_raster`, `run_real_site_risk_raster.py`) and the arcpy steps are untouched.

## Non-goals
1. **No calibration.** `promotion_threshold`, `n_steps`, and the "generation" unit are scenario inputs. The output is an illustrative trajectory. It is not dated, and it is not validated. This is stated on every artifact.
2. No stochastic ensemble in v1. This is an open question. Use a deterministic threshold only, unless a decision changes this.
3. No infection latency. A tree infected in generation `t` is an infectious source in generation `t + 1`.
4. No removal, mortality, or recovery state. Trees are either susceptible or infected. The change is one-way (monotonic). This is an SI process, not SIR.
5. No new spread physics. The dispersal kernel, environmental match, susceptibility, stress, and the wind check work exactly as `compute_risk` uses them now.
6. No seasonality. The environment does not change between generations. The environment grid is static across the whole run.
7. No human-assisted long jumps (firewood, nursery stock). Natural dispersal only, the same as today.
8. `emerald_ash_borer` stays excluded. It has no `spatial_weights` and no real site.
9. No raster temporal loop. `temporal_spread_iteration.md` remains contract-only for that path.

## Open questions (resolve in the design note)
1. **Deterministic vs stochastic promotion.** A deterministic threshold is recommended for v1. It is explainable and reproducible. It matches the raster temporal contract. The stochastic option uses `P(infect) = 1 - exp(-hazard)`, seeded. It would run K realizations and report the per-tree infection frequency and the median infection generation. Should this be a later upgrade, or built now?
2. **`promotion_threshold` per pathogen.** The single-step run peaked at hazard 0.214 for `red_ring_rot` and 0.086 for `anthracnose`. One shared default (say 0.10) would let `red_ring_rot` spread. It would nearly freeze `anthracnose`. The design note sets per-pathogen values. It shows the single-step hazard distribution each value is chosen against.
3. **`n_steps`.** A fixed default (e.g. 12), or run until stalled with a hard cap. Recommendation: run until stalled, with a cap of 25.
4. **Source handling between generations.** Confirm that infected trees are dropped from the susceptible set each generation. They are never re-scored and never reinfected. The `infected` boolean is the only state carried forward.
5. **Frame output format.** Small-multiples PNG, animated GIF, or both. Recommendation: small-multiples PNG for v1. It adds no new dependency and can be reviewed in a diff.
6. **`infected_at_step` for the initial cases.** Either 0 with an "initial case" flag, excluded from spread statistics, or NA. Recommendation: 0 plus the flag.

## Definition of done
1. This contract exists (done).
2. The design note resolves the six open questions (done, `docs/notes/temporal_spread_per_tree.md`).
3. The helper refactor is done. `compute_risk` single-step output is verified unchanged across all three existing runners (done, 2026-09-07).
4. `spread_simulation.py`, `run_real_site_tree_spread.py`, and the `spread_step` config blocks exist and run in the plain `.venv` (done).
5. All three real-site pathogens produce a spread CSV, an epidemic curve, and per-generation map frames (done).
6. Verification recorded below (done, 2026-09-07).

## Verification (2026-09-07)

### Regression (hard gate): PASS
- `_infection_hazard` was extracted from `compute_risk`. The three `outputs/*_site_tree_risk.csv` files are byte-identical before and after.
- `run_prototype.py` and `run_red_ring_rot_grove.py` run clean. Their printed tables are unchanged.
- `run_real_site_risk_raster.py` re-run: risk ranges unchanged (0.000-0.405 / 0.000-0.079 / 0.000-0.229). No tracked `outputs/` file was modified.

### Per-generation trajectory (threshold in parentheses, run until stalled)
- **red_ring_rot** (0.06): 1 initial case. Gen 1: +5. Gen 2: +0, and the run stalls. 5 trees infected over the run.
- **phytophthora** (0.05): 1 initial case. Gen 1: +0, so it stalls immediately. 0 trees. This is a correct null result. The nearest host is 84.6 m away and the dispersal cap is 25 m. This matches `site_tree_host_inventory.md`.
- **anthracnose** (0.035): 2 initial cases. Then +11, +7, +4, +3, +2, +0. That is 6 generations and 27 trees infected. This gives a clean rise-then-fall curve. This is the run that shows a spreading front.

### Distance bound: PASS
Every tree with `infected_at_step == t` is within `t * max_dispersal_distance_m` of an initial case. This holds for both spreading pathogens.

### Why red_ring_rot and anthracnose stall: threshold-sensitive
Neither run runs out of hosts in range. At the stall:
- red_ring_rot: 52 susceptible hosts within 150 m of an infected tree. Best hazard is 0.0512, against a threshold of 0.06.
- anthracnose: 60 susceptible hosts within 200 m. Best hazard is 0.0318, against a threshold of 0.035.

Both stop within ~15% of their threshold. So run length is sensitive to the threshold near these values. This is exactly why the threshold is documented as a knob to sweep, not a calibrated constant. Lowering red_ring_rot to ~0.05 sustains its front. The committed 0.06 is kept because it is the defensible ~p70 value. It was not kept because it produces a longer demo.

### Downwind bias across generations: partially met
Mean `|bearing - downwind|` for spread trees, measured against their nearest initial case:
- red_ring_rot: 37 deg (single-step was ~100 deg). The front moved downwind. Directionality compounds, as predicted. Small n (5).
- anthracnose: 87 deg (single-step was ~73 deg). There is no clearer bias. Its wind directionality strength is only 0.156. The street-tree host geometry (roughly linear sycamore runs) shapes the front more than the weak wind bias does. Success criterion 3's prediction holds for the strongly directional site, not the weakly directional one.

### Explainability
The per-generation log lists every newly infected `tree_id`. A promoted tree's infection can be rebuilt from the prior generation's infected set plus the threshold. `risk_at_infection` in the CSV is the hazard value that cleared the threshold.

### Follow-ups
- red_ring_rot barely spreads at this site (2 generations). The feature is shown by anthracnose. The other two stall for documented reasons: no hosts in range, or a threshold just above the next ring.
- A threshold sweep per pathogen (e.g. 0.02-0.10 in steps) would show how trajectory length and extent respond. This is a natural next what-if tool. It is not built here.
