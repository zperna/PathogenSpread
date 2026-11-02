# Feature contract: Douglas-fir grove red ring rot scenario

## Problem
We need a first site-specific prototype. It must match the setting we have: a Douglas-fir grove where red ring rot is the relevant pathogen.

## Goal
Create a focused prototype scenario. It uses the existing engine, a Douglas-fir-heavy inventory, and the red ring rot pathogen configuration. The project can then produce interpretable risk outputs for a real-world-like setting.

## Scope
- Use the existing generic spread engine.
- Set Douglas-fir as the dominant host species.
- Use the existing red ring rot pathogen settings from the pathogen library.
- Keep the input simple and explainable. It can still be synthetic or placeholder-based.

## Inputs
- A small inventory of trees with at least these fields:
  - tree_id
  - x
  - y
  - species
  - stress_index
  - infected
- A simple environmental surface for moisture and temperature.
- The red ring rot pathogen configuration.

## Outputs
- A ranked list of trees with the highest risk scores.
- A simple explanation of why each tree is flagged, based on:
  - distance to infected source
  - host suitability
  - environmental match
  - stress amplification

## Success criteria
- The prototype runs for a Douglas-fir grove scenario. The core engine does not change.
- The output clearly identifies the most at-risk trees. The output is easy to explain.
- The artifact documents the assumptions and limitations of the scenario.

## Non-goals
- This is not a validated epidemiological model.
- This does not need to include full GIS workflows, wind data, or real disease observations yet.

## Definition of done
The feature is complete when:
- the contract exists,
- the implementation runs end to end,
- and the results are documented in a summary artifact.
