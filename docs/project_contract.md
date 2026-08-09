# Project contract

## Product goal
Build an explainable pathogen spread risk prototype that can evolve from synthetic data into a more realistic decision-support tool.

## Current scope
- Model spread risk from a tree inventory and simple environmental surfaces.
- Keep the engine generic so different pathogens can be configured without rewriting core logic.
- Produce interpretable output that can support triage and field planning.

## Explicit constraints
- The current implementation is a prototype scaffold, not a validated predictive model.
- Assumptions and limitations should be documented clearly.
- New features should improve realism, traceability, or usability without making the system opaque.

## Success criteria for the next milestone
- A clear feature contract exists before implementation.
- The project can run end to end from input data to output risk scores.
- Changes are documented in artifacts that explain what was done and why.

## Planned evolution
1. Prototype baseline: synthetic inventory, simple environmental layers, explainable risk scoring.
2. Data integration: replace synthetic inputs with real inventory or raster data.
3. Realism upgrades: time steps, directional spread, network-based movement, and validation.
4. Decision support: stronger reporting, uncertainty handling, and field-ready outputs.
