# Feature contract: spatial inputs for pathogen risk modeling

## Problem
The current prototype uses synthetic environment surfaces. It does not ingest real spatial data. To move toward a prototype that uses real spatial data, the engine needs a pipeline for land cover, terrain, soil, and moisture inputs.

## Goal
Implement an extensible spatial input pipeline that can:
- read or normalize spatial raster inputs
- sample raster values at tree locations
- convert those values into 0-1 suitability surfaces
- feed the resulting environment data into the existing risk engine

## Scope
- Create a spatial helper module for raster-derived suitability surfaces.
- Extend the environment input dictionary to support land cover, soil, terrain, moisture, and temperature.
- Update the red ring rot prototype runner to demonstrate the new pipeline.
- Keep the core risk engine generic and explainable.

## Inputs
- A tree inventory DataFrame. It has x/y points in a common projected coordinate system.
- Raster layers for land cover, soil, terrain, moisture, and temperature. Placeholders that simulate these layers are also allowed.
- Pathogen config with spatial factor weights.

## Outputs
- Risk scores for each non-infected tree. The spatial suitability components are exposed.
- A site-specific prototype run using the red ring rot scenario.
- Documentation of how raster inputs are prepared and combined.

## Success criteria
- The pipeline maps raster-derived data into the engine's environment dict.
- The prototype run produces risk output that includes spatial suitability components.
- The change is documented in a feature contract and a note artifact.

## Non-goals
- This does not yet implement full hydrological or directional flow modeling.
- This does not require a production GIS engine or database integration.
