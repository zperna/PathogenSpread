# Feature contract: Temporal spread iteration

## Status
Contract only -- not yet implemented. Written to capture the design intent
while it's fresh; implementation is deferred until there's a real reason to
calibrate against (see Non-goals).

## Problem
`compute_risk_raster` (see `docs/feature_contracts/real_site_risk_raster.md`)
produces a single static risk snapshot: "given the known case(s) right now,
where does distance + environment favor spread." It has no time axis --
`decay_rate` and `max_dispersal_distance_m` implicitly assume *some* spread
period, but nothing in the model represents how risk should change over
subsequent seasons or years, or how newly-favorable ground would itself
become a source of further spread.

## Goal
Let the engine express risk as it evolves over discrete time steps, so the
output can show a hotspot plausibly growing/moving outward across a
timeline instead of one frozen picture.

## Scope
- Reuse the existing `compute_risk_raster` dispersal kernel and
  environmental-match logic unchanged -- this is an iteration wrapper
  around it, not new spread physics.
- Each time step: cells whose risk score crosses a configurable promotion
  threshold become additional infection sources for the next step (so
  distance-to-nearest-source keeps shrinking around newly-favorable ground,
  the same way the current single-step version measures distance from the
  original known case).
- The time unit per step (e.g. "one growing season," "one year") and the
  promotion threshold are pathogen-config values, following the existing
  pattern of keeping behavior in `pathogens.py` config dicts rather than
  hard-coded logic.
- Output is a sequence of risk rasters, one per step, so the field-facing
  artifact is "here's how this could look over the next N steps," not a
  single number.

## Inputs
- Everything `compute_risk_raster` already takes (pathogen config,
  environment grid, source points).
- A new per-pathogen `spread_step` config: step time unit (label only, for
  display), `promotion_threshold` (0-1 risk score at which a cell becomes a
  new source), and `n_steps` for a given run.

## Outputs
- A list/stack of 2D risk arrays, one per time step, plus the per-step set
  of newly-promoted source cells (for explainability -- so a step's output
  can be justified by "these N cells crossed threshold last step").

## Success criteria
- Running N steps against the real site grid produces a visibly growing
  (not static, not exploding to fill the whole grid) high-risk area,
  consistent with the pathogen's `max_dispersal_distance_m` per step.
- Each step's newly-promoted sources are inspectable/explainable, not just
  a final black-box raster.
- The single-step `compute_risk_raster` path keeps working unchanged --
  this is additive.

## Non-goals (why this is contract-only for now)
- **No real calibration exists.** There is currently one confirmed red ring
  rot case with no observed date/duration, so there's no data to fit
  `promotion_threshold` or a per-step time unit against actual observed
  spread. Building this now would mean tuning constants against nothing.
- No seasonality/climate-driven infection windows (e.g. red ring rot's
  actual infection biology around wound exposure and moisture timing) --
  would need real moisture/temperature time series, which the project
  doesn't have yet (see `docs/notes/real_site_risk_raster.md`'s known
  limitations).
- No directional spread (wind, water flow direction) -- the dispersal
  kernel stays radially symmetric, same simplification as today.
- No validation against real multi-year progression data.

## Definition of done (for this contract stage)
- This contract exists and is understood as the plan for when temporal
  modeling becomes worth building -- likely once either (a) more confirmed
  cases with dates exist to calibrate against, or (b) the user wants to
  explore "what if" scenarios even without calibration, accepting the
  result as illustrative rather than predictive.
