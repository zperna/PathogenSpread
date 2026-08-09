# Design note: Douglas-fir grove red ring rot prototype

## Approach
Because the only current site information is a Douglas-fir grove with red ring rot, the first implementation should be a scenario-specific prototype rather than a broad geospatial model.

## Design choices
- Reuse the existing generic engine and pathogen configuration system.
- Build a small synthetic inventory that is dominated by Douglas-fir trees.
- Seed a few infected trees to represent the observed disease presence.
- Use the existing environmental raster generation as a placeholder until real site data is available.

## Why this is a good first step
- It keeps the project grounded in the real case we have.
- It preserves the architecture of the current prototype.
- It gives us a concrete, explainable example to discuss and refine.

## Assumptions
- The grove is treated as a local spatial scenario, not a full landscape model.
- The current risk logic is still a simple explainable proxy rather than a calibrated disease model.
- Environmental layers are placeholders until we can bring in actual moisture, temperature, or site condition data.

## Expected outcome
The prototype should show a plausible pattern of elevated risk in Douglas-fir trees nearest the infected source and in trees with higher stress scores.
