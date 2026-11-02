# Design note: temporal spread simulation on the per-tree POS inventory

Companion to `docs/feature_contracts/temporal_spread_per_tree.md`.
Deterministic promotion, confirmed with the user.

## Resolved open questions

1. **Promotion rule: deterministic.** Each generation, a susceptible tree with single-step hazard `>= promotion_threshold` flips to infected. Each (inventory, config, n_steps) combination gives one reproducible trajectory. `simulate_spread` still accepts a `seed` argument. It is unused now. It is reserved for a future stochastic mode, so adding that mode later does not change the signature.

2. **`promotion_threshold` per pathogen.** Set at about the 70th percentile of each pathogen's *nonzero* single-step hazard at its own site. This gives a handful of first-generation promotions. That is enough to seed a front, but not enough to saturate. Measured on the real POS inventory:

   | pathogen | decay | max_disp | nonzero hosts | peak hazard | threshold | gen-1 promotions |
   |---|---|---|---|---|---|---|
   | red_ring_rot | 0.03 | 150 m | 28 | 0.214 | **0.06** | 5 |
   | anthracnose  | 0.02 | 200 m | 46 | 0.086 | **0.035** | ~10 |
   | phytophthora | 0.15 | 25 m  | 0  | -     | **0.05** | 0 |

   `anthracnose`'s hazards run about 2.5x lower than `red_ring_rot`'s at these sites. The main cause is a lower `environmental_match` (about 0.13-0.23 for its top trees). So a shared threshold would either freeze `anthracnose` or over-spread `red_ring_rot`. This is the same "set it per pathogen, do not copy" rule as `spatial_weights`.

   `phytophthora`'s 0.05 is nominal. No host sits inside its 25 m cap, so it produces zero spread. This is the honest result for a parks-only inventory. It is not a bug.

   These are scenario knobs. They are not calibrated infection probabilities. The runner prints them. A user who explores what-ifs should sweep them.

   Config shape in `pathogens.py`: `"spread_step": {"promotion_threshold": <float>, "step_label": "generation"}`.

3. **`n_steps`: run until stalled, hard cap 25.** `simulate_spread(..., n_steps=None)` runs until a generation promotes nothing or the cap is hit. Passing an integer forces that many generations. It still stops early on a stall. The runner passes `None`.

4. **Source handling.** Infected trees are removed from the susceptible set each generation. They are never re-scored and never reinfected. The `infected` boolean is the only state carried between generations, plus the two output columns. This reuses the existing `compute_risk` split unchanged: `sources = df[df.infected]` and `targets = df[~df.infected]`.

5. **Frame output: small-multiples PNG.** One panel per generation, up to 12 panels. A longer run shows every k-th generation, so the grid has at most 12 panels. No animated GIF. No new dependency. It can be reviewed in a diff.

6. **`infected_at_step` for the initial cases: 0**, plus an `is_initial_case` boolean column. All spread statistics (per-generation counts, the distance-bound check, the downwind-bias check) exclude `infected_at_step == 0`.

## Module layout

### `spread_engine.py`: helper refactor (no behavior change)
Extract the per-step core of `compute_risk` into:

```
_infection_hazard(source_xy, targets, pathogen_config, environment, wind)
    -> (risk, components)
```

- `source_xy`: (n_sources, 2) array. `targets`: the non-infected rows (DataFrame) that need `x`, `y`, `species`, `stress_index`.
- Returns `risk` (a 0-1 array, length equal to `len(targets)`). It also returns a `components` dict with the `dispersal_score`, `susceptibility`, `environmental_match`, and `stress_amplification` arrays. These are everything `compute_risk` currently writes as columns.
- It holds the wind check (`transmission_mode in ("airborne", "vector")`), the `_bearing_matrix` / `_dispersal_kernel` call, the `_combine_spatial_environment` call and its moisture/temp fallback, and the stress-amplification term. These are moved, not rewritten.
- `compute_risk` now does this: split sources and targets, return early if either is empty, call `_infection_hazard`, assign the columns exactly as before, and return. Its signature, its return columns, and its numbers are unchanged. This is the one hard regression gate (success criterion 5).

### `spread_simulation.py`: new
```
simulate_spread(inventory, pathogen_config, environment=None, wind=None,
                n_steps=None, seed=None) -> (DataFrame, list[dict])
```
- Copies `inventory`, runs `reset_index(drop=True)`, and coerces `infected` to bool.
- Adds `is_initial_case` (equal to the initial `infected` value), `infected_at_step` (`0` for initial cases, `pd.NA` otherwise), and `risk_at_infection` (`pd.NA`).
- `cap = n_steps if n_steps is not None else 25`.
- For `t` in `1..cap`:
  1. Split sources and targets. Break if either is empty.
  2. `risk, _ = _infection_hazard(...)`.
  3. `mask = risk >= spread_step["promotion_threshold"]`.
  4. If nothing is promoted, log the stalled generation and break.
  5. Otherwise, set `infected`, `infected_at_step = t`, and `risk_at_infection = risk[mask]` on the promoted rows.
  6. Append `{"step": t, "newly_infected": [tree_id...], "cumulative_infected": int}` to the log.
- Returns the augmented DataFrame and the per-generation log.
- Raises a clear error if `pathogen_config` has no `spread_step` block.

### `run_real_site_tree_spread.py`: new, plain `.venv`
- `RUNS` mirrors `run_real_site_tree_risk.py` (`red_ring_rot`/`site`, `phytophthora`/`site_phytophthora`, `anthracnose`/`site_anthracnose`).
- Per run: `build_host_inventory`, `load_site_grid`, load `wind_rose.json` (same helper shape as the risk runner), and `simulate_spread(..., n_steps=None)`.
- Writes:
  - `outputs/<pathogen>_site_tree_spread.csv`: the full inventory plus `is_initial_case`, `infected_at_step`, and `risk_at_infection`. Sorted by `infected_at_step`, with NA last.
  - `outputs/<pathogen>_site_tree_spread_curve.png`: cumulative infected count against generation. Built from the log.
  - `outputs/<pathogen>_site_tree_spread_frames.png`: small-multiples map. Infected trees are colored by `infected_at_step`. Still-susceptible trees are grey. Initial cases are marked with a black x.
- For each run, it prints `promotion_threshold`, the number of generations run, the new and cumulative counts per generation, and the "illustrative what-if, not a forecast" line. Every figure carries the threshold and that caveat in its title or caption.

## Assumptions

1. The per-step hazard is the same quantity `compute_risk` returns today. Iterating it is a modeling choice: an SI process on a point set, with a distance-decay contact kernel. It adds no new physics. The result inherits every existing caveat: placeholder environmental scores, uncalibrated kernel constants, and a static environment.
2. A newly infected tree is fully infectious in the next generation. Real incubation and latency are ignored (contract non-goal 3). A "generation" is an abstract dispersal cycle. It is deliberately not tied to a season or a year.
3. The environment grid and the wind rose are constant across the whole run. There is no seasonal infection window and no year-to-year climate change.
4. Clipping the inventory to the AOI is still complete for the initial step. Every host outside the box is more than max_dispersal from every known case. Across generations, the front could reach the AOI edge. If a run's final-generation infected set touches the boundary, the verification note records it. That run has outgrown the window. It is not a converged result.
5. Deterministic promotion means the trajectory is exact. It is not a mean of realizations. It shows one plausible path, not a probability field. The what-if framing on every artifact is required here.

## Verification plan

1. **Regression (hard gate).** Save the three `outputs/*_site_tree_risk.csv` files. Save the printed tables from `run_prototype.py` and `run_red_ring_rot_grove.py`. Do the helper refactor. Re-run all three existing runners. Confirm the CSVs are byte-identical and the tables match. `run_real_site_risk_raster.py` outputs must be unchanged too. It does not call `compute_risk`, but check anyway.
2. **Distance bound.** For each pathogen, confirm that every tree with `infected_at_step == t` is within `t * max_dispersal_distance_m` of some initial case. A tree outside that bound means the loop is seeding from the wrong set.
3. **Not static, not saturating.** Report the new-infection count for each generation. Expect a rise-then-fall curve, or a rise-then-plateau as the local host pool runs out. Do not expect 0 everywhere. Do not expect all hosts in one step.
4. **anthracnose downwind bias.** Compute the mean bearing of all non-initial infected trees from their nearest initial case. Compare it with the site downwind direction (`prevailing_direction_deg + 180`). Expect a clearer bias than the single-step `|bearing - downwind|` of about 73 deg recorded in `site_tree_host_inventory.md`. The bias should compound each generation.
5. **phytophthora near-zero.** Expect 0 generations of spread at threshold 0.05 (nearest host 84.6 m, cap 25 m). Record this as the correct null outcome.
6. **Explainability spot check.** Pick one promoted tree in a middle generation. Show its nearest infected source from the prior generation. Show the hazard value that cleared the threshold.

## Update summary (2026-09-07)

- Deterministic promotion confirmed. The six open questions are resolved above.
- Implemented: `_infection_hazard` extracted in `spread_engine.py` (`compute_risk` output is byte-identical). Also `spread_simulation.py`, `run_real_site_tree_spread.py`, and `spread_step` blocks for `red_ring_rot` (0.06), `phytophthora` (0.05), and `anthracnose` (0.035) in `pathogens.py`.
- Ran all three. Full results are in the contract's "Verification (2026-09-07)" section. Headline: anthracnose spreads for 6 generations (27 trees, rise-then-fall curve) and is the working demo. Phytophthora produces zero spread, because no host is in its 25 m cap. `red_ring_rot` stalls at generation 2. The next ring of hosts sits about 15% below its threshold.
- Finding not anticipated in this note: the downwind-bias compounding shows clearly only for `red_ring_rot` (wind strength 0.428). It does not show for anthracnose (0.156). The linear street-tree host geometry shapes the anthracnose front more than its weak wind does.
- Deviation from plan: verification is recorded in the contract, not in a separate `docs/notes` file. This matches `site_tree_host_inventory.md` and `anthracnose_site_risk.md`.
