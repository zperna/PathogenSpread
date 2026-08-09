# Feature contract: Real-site risk raster from PathogenProject.gdb

## Problem
All prototype runs so far use synthetic inventories and synthetic environmental
surfaces. We now have real Oregon data staged in ArcGIS Pro
(`PathogenProject.gdb`, `gNATSGO_OR.gdb`, local NLCD land cover, and a live
DEM image service) plus one confirmed red ring rot case (Douglas-fir, point
feature in `RedRingRot`). There is no field tree inventory yet -- only the
single known point.

## Goal
Produce a continuous, explainable red ring rot risk surface over the area
around the known case, built from real land cover, soil drainage, and terrain
data, exportable back into ArcGIS Pro as a GeoTIFF layer.

## Scope
- Export an AOI (2 km square centered on the known case) from the real
  sources into a common CRS/grid the existing engine math can use.
- Reproject everything to a shared **meters**-based CRS (UTM Zone 10N,
  EPSG:32610) -- the source point layer and NLCD are in Oregon Lambert
  **feet** (EPSG:2992), and the engine's dispersal constants
  (`decay_rate`, `max_dispersal_distance_m`) are defined in meters, so unit
  mismatch has to be resolved at export, not silently ignored.
- Derive a soil suitability surface from `gNATSGO_OR.gdb` by joining the
  `MapunitRaster_10m` raster's `MUKEY` to `muaggatt.drclassdcd` (dominant
  drainage class) -- the raster alone only carries a map-unit code, not a
  usable suitability value.
- Export a permanent local DEM clip (source data currently only exists as a
  live ODF ArcGIS Image Service plus an ephemeral Temp-folder derivative) and
  derive Slope and Aspect from that local copy so the pipeline doesn't depend
  on a live external service every run.
- Reuse the existing `spread_engine.py` dispersal kernel and pathogen config
  (`pathogens.py["red_ring_rot"]`) -- no rewrite of the core math.
- Split the work across two Python environments: an arcpy export/import
  script (run under ArcGIS Pro's Python) that only ever reads/writes real
  georeferenced files, and the existing plain `.venv` engine that only reads
  flat numpy/JSON files it's handed. The engine stays arcpy-free.

## Inputs
- `PathogenProject.gdb/RedRingRot`: the known case point (species, infected).
- `PathogenProject/NLCD_2016_Land_Cover_OR/NLCD_2016_Land_Cover_OR.img`: land cover.
- `gNATSGO_OR.gdb/MapunitRaster_10m` + `muaggatt` table: soil drainage class.
- ODF `DEM_Enhanced_10meter_Oregon` ArcGIS Image Service: elevation, for
  slope/aspect derivation.
- `pathogens.py["red_ring_rot"]`: existing pathogen config (dispersal,
  host susceptibility, spatial weights).

## Outputs
- `data/site/grid_meta.json`, `landcover.npy`, `soil_drainage.npy`,
  `slope.npy`, `aspect.npy`, `known_cases.csv`: flat, CRS-free inputs for the
  engine venv.
- `outputs/red_ring_rot_site_risk.npy` + updated `grid_meta.json` copy: the
  computed 0-1 risk surface.
- `outputs/red_ring_rot_site_risk.tif`: the same surface written back out as
  a real georeferenced GeoTIFF (via the arcpy import script) for loading into
  ArcGIS Pro.
- A PNG preview for quick sanity-checking without opening Pro.

## Resolution addendum (2026-08-09)
Output grid resolution was bumped from 30 m (matching NLCD's native resolution)
to 10 m (matching gNATSGO and the DEM's native resolution). NLCD is now
nearest-neighbor *upsampled* to the 10 m grid instead of being the resolution
everything else gets downsampled to -- soil and terrain no longer lose detail
to match land cover. Rationale: with only one known case and a 150 m dispersal
radius, 30 m gave ~5 cells across that radius; 10 m gives ~15, enough to
actually resolve the kernel's falloff shape rather than a blocky approximation.
AOI stays 2 km square, so grids grew from 67x67 to 200x200 cells -- still fast
to compute, no engine changes required (grid handling is resolution-agnostic).

## Success criteria
- The exported grid's known-case cell shows elevated risk that falls off
  with distance in a way consistent with `red_ring_rot`'s
  `max_dispersal_distance_m` (150 m).
- The GeoTIFF opens in ArcGIS Pro in the correct location relative to the
  original `RedRingRot` point and NLCD layer (i.e. the CRS/georeferencing
  round-trip is correct).
- Re-running the export script after the .gdb changes (e.g. more confirmed
  cases added to `RedRingRot`) requires no code changes, only a re-run.

## Non-goals / known limitations this iteration
- No field tree inventory exists yet, so this raster answers "how favorable
  is this location for spread from the known case," not "which specific
  trees are at risk." Host susceptibility and stress amplification (both
  per-tree factors in the existing engine) are **not** applied in raster
  mode -- documented explicitly in code, not silently dropped.
- No real moisture/temperature layers are wired in yet (no climate data
  pulled). `red_ring_rot`'s `environmental_triggers` weights for those are
  left unused this iteration; `spatial_weights` renormalizes across the
  surfaces that are actually provided (land cover, soil, terrain), which the
  engine already supports.
- The slope/aspect -> "terrain suitability" mapping is a simple, documented
  domain assumption (moderate slope + north-facing aspect scores higher, for
  moisture retention), not a validated forest pathology model.
- Soil drainage-class -> suitability score is an ordinal placeholder mapping,
  same caveat as the existing synthetic soil scores it replaces.
- Only one known case exists; this is not a fitted/calibrated model.

## Definition of done
- This contract and its design note exist.
- The arcpy export/import scripts and engine changes run end to end against
  the real `.gdb` data.
- The result (grid stats, output raster, preview) is documented in a
  verification/summary section of the design note.
