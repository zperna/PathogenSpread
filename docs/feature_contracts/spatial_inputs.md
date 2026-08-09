# Feature contract: spatial inputs for pathogen risk modeling

## Problem
The current prototype uses synthetic environment surfaces and does not ingest real spatial data. To move toward a spatially grounded prototype, the engine needs a pipeline for land cover, terrain, soil, and moisture inputs.

## Goal
Implement an extensible spatial input pipeline that can:
- read or normalize spatial raster inputs
- sample raster values at tree locations
- convert those values into 0-1 suitability surfaces
- feed the resulting environment data into the existing risk engine

## Scope
- create a spatial helper module for raster-derived suitability surfaces
- extend the environment input dictionary to support land cover, soil, terrain, moisture, and temperature
- update the red ring rot prototype runner to demonstrate the new pipeline
- keep the core risk engine generic and explainable

## Inputs
- a tree inventory DataFrame with x/y points in a common projected coordinate system
- raster layers for land cover, soil, terrain, moisture, and temperature, or placeholders that simulate them
- pathogen config with spatial factor weights

## Outputs
- risk scores for each non-infected tree, with spatial suitability components exposed
- a site-specific prototype run using the red ring rot scenario
- documentation of how raster inputs are prepared and combined

## Success criteria
- the pipeline can map raster-derived data into the engine's environment dict
- the prototype run produces risk output that includes spatial suitability components
- the change is documented in a feature contract and note artifact

## Non-goals
- this does not yet implement full hydrological or directional flow modeling
- this does not require a production GIS engine or database integration
