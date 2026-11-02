# Feature contract: Temporal spread iteration

## Status
Contract only. It is not implemented, and it stays that way for the *raster* path. It was written to capture the design intent while the idea was fresh. Implementation waits until there is a real reason to calibrate against (see Non-goals).

The per-tree version of this idea is now a separate active contract. See `docs/feature_contracts/temporal_spread_per_tree.md`. It iterates `compute_risk` over the real POS host inventory as an explicit what-if scenario. That contract also notes that this one's "no directional spread" non-goal is stale. The wind-aware kernel now exists.

## Problem
`compute_risk_raster` (see `docs/feature_contracts/real_site_risk_raster.md`) produces a single static risk snapshot. It answers: "given the known case(s) right now, where does distance + environment favor spread." It has no time axis. `decay_rate` and `max_dispersal_distance_m` implicitly assume *some* spread period. But the model does not represent how risk changes over later seasons or years. It also does not represent how newly favorable ground becomes a source of further spread.

## Goal
Let the engine express risk as it changes over discrete time steps. The output can then show a hotspot that plausibly grows or moves outward over a timeline. A single static picture does not do this.

## Scope
- Reuse the existing `compute_risk_raster` dispersal kernel and environmental-match logic unchanged. This is an iteration wrapper around it. It adds no new spread physics.
- Each time step: cells whose risk score crosses a configurable promotion threshold become additional infection sources for the next step. So distance-to-nearest-source keeps shrinking around newly favorable ground. The current single-step version measures distance from the original known case in the same way.
- The time unit per step (e.g. "one growing season," "one year") and the promotion threshold are pathogen-config values. This follows the existing pattern. Behavior lives in `pathogens.py` config dicts, not in hard-coded logic.
- Output is a sequence of risk rasters, one per step. The field-facing artifact answers "here's how this could look over the next N steps." It is not a single number.

## Inputs
- Everything `compute_risk_raster` already takes (pathogen config, environment grid, source points).
- A new per-pathogen `spread_step` config with three keys: step time unit (label only, for display), `promotion_threshold` (0-1 risk score at which a cell becomes a new source), and `n_steps` for a given run.

## Outputs
- A list or stack of 2D risk arrays, one per time step. Also the per-step set of newly promoted source cells. This supports explainability. A step's output can be justified by "these N cells crossed the threshold last step."

## Success criteria
- Running N steps against the real site grid produces a visibly growing high-risk area. It must not stay static. It must not fill the whole grid. Its growth is consistent with the pathogen's `max_dispersal_distance_m` per step.
- Each step's newly promoted sources can be inspected and explained. The output is not a final black-box raster.
- The single-step `compute_risk_raster` path keeps working unchanged. This change is additive.

## Non-goals (why this is contract-only for now)
- **No real calibration exists.** There is one confirmed red ring rot case. It has no observed date or duration. So there is no data to fit `promotion_threshold` or a per-step time unit against observed spread. Building this now would mean tuning constants against nothing.
- No seasonality or climate-driven infection windows. An example is red ring rot's infection biology around wound exposure and moisture timing. Those need real moisture and temperature time series. The project does not have them yet (see `docs/notes/real_site_risk_raster.md`'s known limitations).
- No directional spread (wind, water flow direction). The dispersal kernel stays radially symmetric. This is the same simplification as today.
- No validation against real multi-year progression data.

## Definition of done (for this contract stage)
- This contract exists. It is the plan for when temporal modeling becomes worth building. That is likely once either (a) more confirmed cases with dates exist to calibrate against, or (b) the user wants to explore "what if" scenarios without calibration. In case (b), the user accepts the result as illustrative, not predictive.
