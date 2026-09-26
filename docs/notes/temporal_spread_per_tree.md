# Design note: temporal spread simulation on the per-tree POS inventory

Companion to `docs/feature_contracts/temporal_spread_per_tree.md`.
Deterministic promotion, confirmed with the user.

## Resolved open questions

1. **Promotion rule: deterministic.** Each generation, a susceptible
   tree with single-step hazard `>= promotion_threshold` flips to
   infected. One reproducible trajectory per (inventory, config,
   n_steps). `simulate_spread` still accepts a `seed` argument; it is
   unused now and reserved for a future stochastic mode so adding that
   later does not change the signature.

2. **`promotion_threshold` per pathogen.** Set at roughly the 70th
   percentile of each pathogen's *nonzero* single-step hazard at its own
   site, which yields a handful of first-generation promotions -- enough
   to seed a front, not enough to saturate. Measured on the real POS
   inventory:

   | pathogen | decay | max_disp | nonzero hosts | peak hazard | threshold | gen-1 promotions |
   |---|---|---|---|---|---|---|
   | red_ring_rot | 0.03 | 150 m | 28 | 0.214 | **0.06** | 5 |
   | anthracnose  | 0.02 | 200 m | 46 | 0.086 | **0.035** | ~10 |
   | phytophthora | 0.15 | 25 m  | 0  | -     | **0.05** | 0 |

   `anthracnose`'s hazards run about 2.5x lower than `red_ring_rot`'s at
   these sites -- mostly a lower `environmental_match` (about 0.13-0.23
   for its top trees) -- so a shared threshold would either freeze
   `anthracnose` or over-spread `red_ring_rot`. This is the same
   "reason it per pathogen, do not copy" discipline as `spatial_weights`.
   `phytophthora`'s 0.05 is nominal: with no host inside its 25 m cap it
   will produce zero spread, which is the honest result for a parks-only
   inventory, not a bug.

   These are scenario knobs, not calibrated infection probabilities. The
   runner prints them and a user exploring what-ifs should sweep them.
   Config shape in `pathogens.py`:
   `"spread_step": {"promotion_threshold": <float>, "step_label": "generation"}`.

3. **`n_steps`: run until stalled, hard cap 25.** `simulate_spread(...,
   n_steps=None)` runs until a generation promotes nothing or the cap is
   hit. Passing an integer forces that many generations (still breaking
   early on a stall). The runner passes `None`.

4. **Source handling.** Infected trees are removed from the susceptible
   set each generation -- never re-scored, never reinfected. The
   `infected` boolean is the only state carried between generations
   (plus the two output columns). This reuses `compute_risk`'s existing
   `sources = df[df.infected]` / `targets = df[~df.infected]` split
   verbatim.

5. **Frame output: small-multiples PNG.** One panel per generation, up
   to 12 panels; a longer run shows every k-th generation so the grid
   stays <= 12. No animated GIF, no new dependency, and it diffs in
   review.

6. **`infected_at_step` for the initial cases: 0**, plus an
   `is_initial_case` boolean column. All spread statistics (per-
   generation counts, the distance-bound check, the downwind-bias check)
   exclude `infected_at_step == 0`.

## Module layout

### `spread_engine.py` -- helper refactor (no behavior change)
Extract the per-step core of `compute_risk` into:

```
_infection_hazard(source_xy, targets, pathogen_config, environment, wind)
    -> (risk, components)
```

- `source_xy`: (n_sources, 2) array. `targets`: the non-infected rows
  (DataFrame) needing `x`, `y`, `species`, `stress_index`.
- Returns `risk` (0-1 array, len == len(targets)) and `components`
  dict of `dispersal_score`, `susceptibility`, `environmental_match`,
  `stress_amplification` arrays -- everything `compute_risk` currently
  writes as columns.
- Holds the wind gate (`transmission_mode in ("airborne", "vector")`),
  the `_bearing_matrix` / `_dispersal_kernel` call, the
  `_combine_spatial_environment` call and its moisture/temp fallback,
  and the stress-amplification term -- moved, not rewritten.
- `compute_risk` becomes: split sources/targets, early-return on either
  empty, call `_infection_hazard`, assign the columns exactly as now,
  return. Its signature, its return columns, and its numbers are
  unchanged. This is the one hard regression gate (success criterion 5).

### `spread_simulation.py` -- new
```
simulate_spread(inventory, pathogen_config, environment=None, wind=None,
                n_steps=None, seed=None) -> (DataFrame, list[dict])
```
- Copies `inventory`, `reset_index(drop=True)`, coerces `infected` to
  bool.
- Adds `is_initial_case` (= initial `infected`), `infected_at_step`
  (`0` for initial cases, `pd.NA` otherwise), `risk_at_infection`
  (`pd.NA`).
- `cap = n_steps if n_steps is not None else 25`.
- For `t` in `1..cap`: split sources/targets; break if either empty;
  `risk, _ = _infection_hazard(...)`; `mask = risk >=
  spread_step["promotion_threshold"]`; if nothing promoted, log the
  stalled generation and break; else set `infected`,
  `infected_at_step = t`, `risk_at_infection = risk[mask]` on the
  promoted rows; append `{"step": t, "newly_infected": [tree_id...],
  "cumulative_infected": int}` to the log.
- Returns the augmented DataFrame and the per-generation log.
- Raises a clear error if `pathogen_config` has no `spread_step` block.

### `run_real_site_tree_spread.py` -- new, plain `.venv`
- `RUNS` mirrors `run_real_site_tree_risk.py`
  (`red_ring_rot`/`site`, `phytophthora`/`site_phytophthora`,
  `anthracnose`/`site_anthracnose`).
- Per run: `build_host_inventory`, `load_site_grid`, load
  `wind_rose.json` (same helper shape as the risk runner),
  `simulate_spread(..., n_steps=None)`.
- Writes:
  - `outputs/<pathogen>_site_tree_spread.csv` -- full inventory +
    `is_initial_case`, `infected_at_step`, `risk_at_infection`, sorted
    by `infected_at_step` (NA last).
  - `outputs/<pathogen>_site_tree_spread_curve.png` -- cumulative
    infected vs generation, from the log.
  - `outputs/<pathogen>_site_tree_spread_frames.png` -- small-multiples
    map, infected trees colored by `infected_at_step`, still-susceptible
    grey, initial cases marked black x.
- Prints, per run: `promotion_threshold`, generations run, per-
  generation new/cumulative counts, and the "illustrative what-if, not
  a forecast" line. Every figure carries the threshold and that caveat
  in its title or caption.

## Assumptions

1. The per-step hazard is the same quantity `compute_risk` returns
   today. Iterating it is a modeling choice (an SI process on a point
   set with a distance-decay contact kernel), not new physics. The
   result inherits every existing caveat: placeholder environmental
   scores, uncalibrated kernel constants, a static environment.
2. A newly infected tree is fully infectious the next generation. Real
   incubation/latency is ignored (contract non-goal 3), so a "generation"
   is an abstract dispersal cycle, deliberately not tied to a season or
   a year.
3. The environment grid and the wind rose are constant across the whole
   run. No seasonal infection window, no year-to-year climate change.
4. Clipping the inventory to the AOI is still complete for the initial
   step (every out-of-box host is > max_dispersal from every known
   case). Across generations the front could in principle reach the AOI
   edge; if a run's final-generation infected set touches the boundary,
   the verification note records it as a run that has outgrown the
   window rather than a converged result.
5. Deterministic promotion means the trajectory is exact, not a mean of
   realizations. It shows one plausible path, not a probability field.
   The what-if framing on every artifact is load-bearing here.

## Verification plan

1. **Regression (hard gate).** Save the three
   `outputs/*_site_tree_risk.csv` and the `run_prototype.py` /
   `run_red_ring_rot_grove.py` printed tables, do the helper refactor,
   re-run all three existing runners, confirm the CSVs are byte-
   identical and the tables match. `run_real_site_risk_raster.py`
   outputs unchanged too (it does not touch `compute_risk`, but check).
2. **Distance bound.** For each pathogen, confirm every tree with
   `infected_at_step == t` is within `t * max_dispersal_distance_m` of
   some initial case. A tree outside that bound means the loop is
   seeding from the wrong set.
3. **Not static, not saturating.** Per-generation new-infection counts
   are reported. Expect a rise-then-fall (or rise-then-plateau as the
   local host pool is exhausted), not 0 everywhere and not "all hosts in
   one step".
4. **anthracnose downwind bias.** Mean bearing of all non-initial
   infected trees from their nearest initial case, compared with the
   site downwind direction (`prevailing_direction_deg + 180`). Expect a
   clearer lean than the single-step `|bearing - downwind|` ~73 deg
   recorded in `site_tree_host_inventory.md`, because the bias compounds
   each generation.
5. **phytophthora near-zero.** Expect 0 generations of spread at
   threshold 0.05 (nearest host 84.6 m, cap 25 m). Recorded as the
   correct null outcome.
6. **Explainability spot check.** Pick one promoted tree in a middle
   generation, show its nearest infected source from the prior
   generation and the hazard value that cleared the threshold.

## Update summary (2026-09-07)

- Deterministic promotion confirmed; six open questions resolved above.
- Implemented: `_infection_hazard` extracted in `spread_engine.py`
  (compute_risk output byte-identical), `spread_simulation.py`,
  `run_real_site_tree_spread.py`, and `spread_step` blocks for
  `red_ring_rot` (0.06), `phytophthora` (0.05), `anthracnose` (0.035)
  in `pathogens.py`.
- Ran all three. Full results in the contract's "Verification
  (2026-09-07)" section. Headline: anthracnose spreads for 6 generations
  (27 trees, rise-then-fall curve) and is the working demo; phytophthora
  produces zero spread (no host in its 25 m cap); red_ring_rot stalls at
  generation 2 because the next ring of hosts sits ~15% below its
  threshold.
- Finding not anticipated in this note: the downwind-bias compounding
  shows clearly only for red_ring_rot (wind strength 0.428), not
  anthracnose (0.156) -- the linear street-tree host geometry drives the
  anthracnose front more than its weak wind does.
- Deviation from plan: verification recorded in the contract, not a
  separate `docs/notes` file (matches `site_tree_host_inventory.md` and
  `anthracnose_site_risk.md`).
