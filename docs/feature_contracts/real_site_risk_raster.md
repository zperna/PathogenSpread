# Feature contract: Real-site risk raster from PathogenProject.gdb

## Problem
All prototype runs so far use synthetic inventories and synthetic environmental surfaces. We now have real Oregon data staged in ArcGIS Pro (`PathogenProject.gdb`, `gNATSGO_OR.gdb`, local NLCD land cover, and a live DEM image service). We also have one confirmed red ring rot case (Douglas-fir, point feature in `RedRingRot`). There is no field tree inventory yet. Only the single known point exists.

## Goal
Produce a continuous, explainable red ring rot risk surface over the area around the known case. Build it from real land cover, soil drainage, and terrain data. Export it back into ArcGIS Pro as a GeoTIFF layer.

## Scope
- Export an AOI (2 km square centered on the known case) from the real sources. Use a common CRS and grid that the existing engine math can use.
- Reproject everything to a shared **meters**-based CRS (UTM Zone 10N, EPSG:32610). The source point layer and NLCD use Oregon Lambert **feet** (EPSG:2992). The engine's dispersal constants (`decay_rate`, `max_dispersal_distance_m`) use meters. The unit mismatch must be resolved at export. It must not be ignored.
- Derive a soil suitability surface from `gNATSGO_OR.gdb`. Join the `MapunitRaster_10m` raster's `MUKEY` to `muaggatt.drclassdcd` (dominant drainage class). The raster alone carries only a map-unit code. It does not carry a usable suitability value.
- Export a permanent local DEM clip. The source data currently exists only as a live ODF ArcGIS Image Service and an ephemeral Temp-folder derivative. Derive Slope and Aspect from the local copy. The pipeline then does not depend on a live external service on every run.
- Reuse the existing `spread_engine.py` dispersal kernel and pathogen config (`pathogens.py["red_ring_rot"]`). Do not rewrite the core math.
- Split the work across two Python environments. The arcpy export and import script runs under ArcGIS Pro's Python. It reads and writes only real georeferenced files. The existing plain `.venv` engine reads only the flat numpy and JSON files it is handed. The engine stays arcpy-free.

## Inputs
- `PathogenProject.gdb/RedRingRot`: the known case point (species, infected).
- `PathogenProject/NLCD_2016_Land_Cover_OR/NLCD_2016_Land_Cover_OR.img`: land cover.
- `gNATSGO_OR.gdb/MapunitRaster_10m` and the `muaggatt` table: soil drainage class.
- ODF `DEM_Enhanced_10meter_Oregon` ArcGIS Image Service: elevation, for slope and aspect derivation.
- `pathogens.py["red_ring_rot"]`: existing pathogen config (dispersal, host susceptibility, spatial weights).

## Outputs
- `data/site/grid_meta.json`, `landcover.npy`, `soil_drainage.npy`, `slope.npy`, `aspect.npy`, and `known_cases.csv`. These are flat, CRS-free inputs for the engine venv.
- `outputs/red_ring_rot_site_risk.npy` and an updated copy of `grid_meta.json`. These hold the computed 0-1 risk surface.
- `outputs/red_ring_rot_site_risk.tif`. The same surface, written back out as a georeferenced GeoTIFF by the arcpy import script. Load it into ArcGIS Pro.
- A PNG preview for quick sanity checks without opening Pro.

## Resolution addendum (2026-08-09)
Output grid resolution changed from 30 m to 10 m. The earlier 30 m value matched NLCD's native resolution. The 10 m value matches gNATSGO and the DEM's native resolution.

NLCD is now nearest-neighbor *upsampled* to the 10 m grid. Before, all other layers were downsampled to match NLCD. Soil and terrain no longer lose detail to match land cover.

Rationale: with only one known case and a 150 m dispersal radius, 30 m gave about 5 cells across that radius. 10 m gives about 15. That is enough to resolve the falloff shape of the kernel. It avoids a blocky approximation.

The AOI stays 2 km square. Grids grew from 67x67 to 200x200 cells. This is still fast to compute. No engine changes are needed, because grid handling does not depend on resolution.

## Success criteria
- The exported grid's known-case cell shows elevated risk. Risk falls off with distance in a way that matches `red_ring_rot`'s `max_dispersal_distance_m` (150 m).
- The GeoTIFF opens in ArcGIS Pro at the correct location. It must line up with the original `RedRingRot` point and the NLCD layer. That is, the CRS and georeferencing round trip is correct.
- Re-running the export script after the .gdb changes (for example, after more confirmed cases are added to `RedRingRot`) needs no code changes. It needs only a re-run.

## Non-goals and known limitations this iteration
- No field tree inventory exists yet. This raster answers "how favorable is this location for spread from the known case." It does not answer "which specific trees are at risk." Host susceptibility and stress amplification are both per-tree factors in the existing engine. They are **not** applied in raster mode. The code documents this explicitly. It is not silently dropped.
- No real moisture or temperature layers are wired in yet. No climate data was pulled. The `environmental_triggers` weights for those in `red_ring_rot` are unused this iteration. `spatial_weights` renormalizes across the surfaces that are provided (land cover, soil, terrain). The engine already supports this.
- The mapping from slope and aspect to "terrain suitability" is a simple, documented domain assumption. Moderate slope and north-facing aspect score higher, for moisture retention. It is not a validated forest pathology model.
- The mapping from soil drainage class to suitability score is an ordinal placeholder. It carries the same caveat as the synthetic soil scores it replaces.
- Only one known case exists. This is not a fitted or calibrated model.

## Definition of done
- This contract and its design note exist.
- The arcpy export and import scripts and the engine changes run end to end against the real `.gdb` data.
- The result (grid stats, output raster, preview) is documented in a verification or summary section of the design note.
