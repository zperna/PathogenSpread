# Project contract

## Product goal
Build an explainable pathogen spread risk prototype. It can evolve from synthetic data into a more realistic decision-support tool.

## Current scope
- Model spread risk from a tree inventory and simple environmental surfaces.
- Keep the engine generic. Different pathogens can be configured without rewriting core logic.
- Produce interpretable output that can support triage and field planning.

## Explicit constraints
- The current implementation is a prototype scaffold. It is not a validated predictive model.
- Document assumptions and limitations clearly.
- New features should improve realism, traceability, or usability. They should not make the system opaque.

## Success criteria for the next milestone
- A clear feature contract exists before implementation.
- The project runs end to end, from input data to output risk scores.
- Changes are documented in artifacts. The artifacts explain what was done and why.

## Planned evolution
1. Prototype baseline: synthetic inventory, simple environmental layers, explainable risk scoring.
2. Data integration: replace synthetic inputs with real inventory or raster data.
3. Realism upgrades: time steps, directional spread, network-based movement, and validation.
4. Decision support: stronger reporting, uncertainty handling, and field-ready outputs.

## Future possibilities
These items come from the project review on 2026-11-09. Each one needs its own feature contract before implementation. The evidence for each item is in docs/summaries/test_suite_and_review_2026_11_09.md.

1. Per-pathogen land cover scores.
   - Problem: one NLCD score map serves all pathogens. It rates evergreen forest above deciduous forest, but the anthracnose hosts are deciduous. It also gives low scores to developed land, where most inventory trees stand.
   - Possibility: move the NLCD score map into each pathogen config. For the per-tree path, replace land cover with host density calculated from the inventory.
2. Full wind rose kernel.
   - Problem: the kernel uses one mean wind direction. The Eugene wind rose has two peaks (north and south), and the mean direction (225 degrees) matches neither. The strength value also ignores calm observations.
   - Possibility: weight dispersal by the 36 sector frequencies that wind_rose.json already stores. Include the calm percent in the strength. Fetch a seasonal wind rose for pathogens with a seasonal dispersal period.
3. Stochastic spread mode.
   - Problem: the spread simulation is deterministic, and its result changes sharply with promotion_threshold. The `seed` argument has no effect.
   - Possibility: treat the single-step hazard as an infection probability. Run many trials with `seed`. Report an infection frequency for each tree in place of one trajectory.
4. Validation by hindcast.
   - Problem: each site has 1 or 2 known cases. No output is compared with observed spread.
   - Possibility: get dated case records. Hide the later cases, run the model on the earlier cases, and measure how well the model ranks the hidden cases.
5. Real stress and host data.
   - Problem: stress_index is 0 for every real tree. The phytophthora known case is a Port Orford cedar, which is not in the phytophthora host list. Emerald ash borer has no real site.
   - Possibility: derive stress_index from tree diameter, canopy condition imagery, or drought layers. Align the phytophthora host list with the known case, or select a different site. Add an emerald ash borer site when a confirmed case exists.
