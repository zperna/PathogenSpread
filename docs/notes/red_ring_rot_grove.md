# Design note: Douglas-fir grove red ring rot prototype

## Approach
The only current site information is a Douglas-fir grove with red ring rot. So the first implementation is a scenario-specific prototype. It is not a broad geospatial model.

## Design choices
- Reuse the existing generic engine and pathogen configuration system.
- Build a small synthetic inventory. Douglas-fir trees dominate it.
- Seed a few infected trees. They represent the observed disease presence.
- Use the existing environmental raster generation as a placeholder until real site data is available.

## Why this is a good first step
- It keeps the project tied to the real case we have.
- It preserves the architecture of the current prototype.
- It gives us a concrete, explainable example to discuss and refine.

## Assumptions
- The grove is a local spatial scenario. It is not a full landscape model.
- The current risk logic is a simple explainable proxy. It is not a calibrated disease model.
- Environmental layers are placeholders. They stay placeholders until we bring in actual moisture, temperature, or site condition data.

## Expected outcome
The prototype should show a plausible pattern. Risk is elevated in Douglas-fir trees nearest the infected source. Risk is also elevated in trees with higher stress scores.
