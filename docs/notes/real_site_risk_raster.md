# Design note: Real-site risk raster

## Approach
Split the pipeline at the arcpy boundary rather than adding arcpy as a
dependency of the engine:

1. **`PathogenPy/arcpy_export/export_site_layers.py`** -- run once (or
   re-run when the .gdb changes) under ArcGIS Pro's Python
   (`...\ArcGIS\Pro\bin\Python\envs\arcgispro-py3\python.exe`). Reads the
   real sources, reprojects everything to a shared meters CRS, clips to a
   2 km AOI around the known case, and writes flat files: numpy arrays for
   each surface, a `grid_meta.json` describing the grid's real-world origin
   and resolution, and `known_cases.csv` for point data. No arcpy-specific
   objects leak past this script.
2. **The existing `.venv` engine** reads only those flat files. It never
   touches arcpy, rasterio, or any CRS object -- it just needs an
   `(origin_x, origin_y, resolution_m)` anchor instead of assuming the grid
   starts at `(0, 0)` like the synthetic surfaces do.
3. **`PathogenPy/arcpy_export/import_risk_raster.py`** -- run under arcpy
   again, after the engine produces a risk array, to write it back out as a
   real georeferenced GeoTIFF using the same origin/resolution/CRS recorded
   in `grid_meta.json`.

## Design choices

### CRS and units
Source layers are split across three CRSs (Oregon Lambert feet for the point
and NLCD, Albers CONUS meters for gNATSGO, geographic/web-mercator-ish for
the DEM image service). The engine's dispersal constants are defined in
meters. Rather than teach the engine to handle units/CRS, the export script
resolves this once: everything is reprojected to UTM Zone 10N (EPSG:32610,
meters) at export time. The engine only ever sees meters, matching how the
synthetic prototype already worked.

### Grid representation stays simple
`spread_engine.py`'s existing raster sampling (`_sample_grid_at_points`)
indexes a square grid by dividing local coordinates by `area_size_m`. Rather
than rewriting this to carry a full affine transform, the export script
guarantees every layer shares one CRS, one resolution, and one aligned
extent, and records the grid's real-world lower-left corner as
`origin_x`/`origin_y` in `grid_meta.json`. The engine change is additive: sampling
subtracts the origin before the existing divide-by-`area_size_m` math, and
`origin_x`/`origin_y` default to `0` so all existing synthetic-data code
paths and tests are unaffected.

### Soil: raster + table join, not a raw raster
`MapunitRaster_10m` only stores a `MUKEY` code per cell -- not a usable
suitability value. The export script joins each cell's `MUKEY` to
`muaggatt.drclassdcd` (the 7-class USDA dominant drainage class) and writes
an integer class-code raster plus a small crosswalk. `spatial_inputs.py`
turns the 7 classes into a 0-1 suitability score using an ordinal mapping
(wetter = more favorable for this fungal pathogen, consistent with the
existing placeholder soil scoring it replaces):

    Excessively drained        -> 0.15
    Somewhat excessively drained -> 0.25
    Well drained                -> 0.35
    Moderately well drained     -> 0.55
    Somewhat poorly drained     -> 0.75
    Poorly drained              -> 0.90
    Very poorly drained         -> 1.00

### Terrain: derive locally, don't depend on a live service
The DEM only exists as a live ODF Image Service in the current Pro project
(plus an ephemeral Temp-folder raster-function cache that will get cleaned
up). The export script pulls a permanent local DEM clip for the AOI once,
then runs `arcpy.sa.Slope`/`arcpy.sa.Aspect` on that local copy. Terrain
suitability is a simple, explicitly-labeled placeholder: moderate slope
(more moisture retention than very steep, better-drained slopes) and
north-facing aspect (cooler, damper) score higher. This is a documented
domain assumption, not validated pathology.

### Raster risk mode is new, not a repurposing of point scoring
`compute_risk` (point-based) assumes each row has a `species` and
`stress_index` -- there's no equivalent for a raster cell. Rather than
stretch those semantics, this adds `compute_risk_raster()`: same dispersal
kernel and environmental-match logic, applied to every grid cell instead of
every tree row, with host susceptibility and stress amplification left out
and documented as out of scope (see contract's Non-goals). This keeps the
existing `compute_risk` untouched -- the Douglas-fir grove synthetic
prototype still works exactly as before.

## Assumptions
- A 2 km AOI around the known case is large enough to show the dispersal
  kernel's falloff (150 m max) with useful surrounding context, small enough
  to keep the export fast.
- ~~30 m output resolution (matching native NLCD) is an acceptable common grid
  resolution, even though gNATSGO is natively 10 m and the DEM is ~10 m --
  those get resampled down at export.~~ Superseded 2026-08-09: bumped to
  10 m (matching gNATSGO/DEM native resolution) so the 150 m dispersal
  kernel resolves across ~15 cells instead of ~5; NLCD is now the layer
  that gets resampled (nearest-neighbor upsampled), not the other way
  around. See the contract's Resolution addendum.
- Moisture/temperature spatial weights are left unused this iteration (no
  real climate layer yet); `_combine_spatial_environment`'s existing
  renormalize-over-available-surfaces behavior handles this without engine
  changes.

## Expected outcome
A GeoTIFF centered on the known Douglas-fir case showing a ring of elevated
risk near the point that fades within ~150 m, modulated by land cover, soil
drainage, and terrain -- suitable for loading back into
`PathogenProject.aprx` as a sanity-checkable layer.

## Verification

Ran end to end against the real data on 2026-08-08:

- `export_site_layers.py` (ArcGIS Pro Python) exported a 67x67 cell, 30 m
  grid centered on the one `RedRingRot` known case (Douglas-fir / `PsMe`) to
  `data/site/`, plus reference GeoTIFFs to `data/site/gis_reference/`.
- `run_real_site_risk_raster.py` (`.venv`) computed the risk raster: range
  0.000-0.310, mean 0.001, peak at the known case's cell. Saved
  `outputs/red_ring_rot_site_risk.npy` and a preview PNG showing a tight
  hotspot at the known point fading out well within the AOI, consistent
  with `red_ring_rot`'s 150 m `max_dispersal_distance_m`.
- `import_risk_raster.py` (ArcGIS Pro Python) converted that array back to
  `outputs/red_ring_rot_site_risk.tif` (EPSG:32610). Confirmed the
  georeferencing round-trip: sampling the GeoTIFF at the known case's real
  UTM coordinate (`GetCellValue`) returned 0.310 -- the same peak value
  computed in the engine, at the same real-world location as the original
  `RedRingRot` point. All three of the contract's success criteria are met.
- Regression check: both existing synthetic prototypes
  (`run_prototype.py`, `run_red_ring_rot_grove.py`) still run unchanged and
  produce the same kind of output as before -- the grid-origin and raster
  sampling changes in `spread_engine.py` didn't affect the synthetic
  (origin `0,0`) code path.

### Problems hit and fixed along the way
- **AOI clipping silently no-op'd**: the `arcpy.Extent` built for the AOI
  had no coordinate system attached. Depending on environment-setting
  order, ArcGIS misread the meter-based bounds and fell back to processing
  the *entire* NLCD raster (27,665 x 30,643 cells) instead of the 2 km AOI.
  Fixed by attaching `spatial_reference=TARGET_SR` directly on the `Extent`
  object at construction, not relying on `arcpy.env.outputCoordinateSystem`
  alone.
- **DEM clip hung indefinitely**: `arcpy.management.Clip` against the live
  ODF `ImageServer` URL took ~4 seconds in isolation, but hung for over an
  hour inside the full script. Root cause: leftover
  `arcpy.env.extent`/`outputCoordinateSystem`/`cellSize` from the land
  cover and soil steps (a different CRS/extent than the DEM service's own)
  were still active when the DEM step started. Fixed by explicitly
  resetting those three environment settings to `None` right before the
  live-service `Clip` call.
- **Cross-CRS pixel misalignment**: reprojecting land cover (from Oregon
  Lambert feet) landed on a slightly different pixel grid (73x72) than soil
  and terrain (from Albers/feet DEM, both 67x67) for the identical
  requested extent -- an expected side effect of reprojecting between CRSs
  without an explicit snap raster. Fixed pragmatically for this prototype
  by cropping all layers to their common origin-aligned shape rather than
  chasing exact ArcGIS pixel snapping; the crop point is logged, not silent.

## Update summary
Real Oregon data (NLCD land cover, gNATSGO soil drainage, ODF DEM-derived
slope/aspect, and the one confirmed red ring rot case) now flows through the
existing engine via a new raster-risk mode, producing a GeoTIFF that opens
correctly in `PathogenProject.aprx`. The synthetic Douglas-fir grove
prototype is untouched and still works. Next iteration candidates: a real
field tree inventory (to re-enable host susceptibility/stress
amplification and per-tree scoring), real moisture/temperature layers, and
replacing the placeholder slope/aspect and drainage-class scoring with
something grounded in actual forest pathology guidance rather than ordinal
domain judgment.

### Resolution bump to 10 m -- verification (2026-08-09)
Re-ran the full three-stage pipeline (`export_site_layers.py` ->
`run_real_site_risk_raster.py` -> `import_risk_raster.py`) after changing
`CELL_SIZE_M` from 30 to 10 in `export_site_layers.py`. Both sites now export
200x200 cell grids (up from 67x67); the origin-corner pixel-alignment crop
(landcover lands a few cells off from soil/terrain due to cross-CRS
reprojection, same as before) still triggers as expected and is logged.

- `red_ring_rot`: risk range 0.000-0.472 (was 0.000-0.310 at 30 m), mean
  0.001, peak still at the known case's cell. The higher peak is expected,
  not a regression: at 30 m the known-case cell's environmental suitability
  was averaged/resampled across a coarser footprint; at 10 m it reflects a
  smaller, more localized area right at the point.
- `phytophthora`: risk range 0.000-0.133, mean 0.000, peak at the known
  case's cell.
- `import_risk_raster.py` round-tripped both back to 10 m GeoTIFFs
  (`outputs/red_ring_rot_site_risk.tif`, `outputs/phytophthora_site_risk.tif`)
  under the same EPSG:32610 CRS as before -- no code changes needed there,
  since resolution is read from each run's `grid_meta.json` rather than
  hardcoded.
- Regression check: `spread_engine.py`'s grid sampling and raster-risk code
  took no changes for this -- resolution was already a `grid_meta.json`
  parameter, not hardcoded, so this was purely a data re-export plus
  re-run, not an engine change.

### Preview scaling fix (2026-08-14)
The resolution bump's finer-grained structure was real but invisible in
`run_real_site_risk_raster.py`'s preview PNG: it plotted the full 2km AOI
with a fixed 0-1 color scale shared across pathogens, so phytophthora's
~40m-wide, 0.13-peak footprint rendered as a flat pale rectangle --
indistinguishable from "nothing here." Confirmed via a throwaway diagnostic
script that the raster itself had real, asymmetric structure (16 distinct
nonzero cells, peak cell offset from the known case's literal point location
due to soil/terrain modulation) that the shipped preview simply couldn't
show at that scale.

Fixed `run_one()`'s plotting to crop to the risk footprint (bounding box of
nonzero cells + source points, padded 10 cells) and auto-scale the color
range to that window's own data instead of a fixed 0-1 scale, with the
actual peak value in the title. Re-ran both pathogens:
- `phytophthora`: now shows a clean, tight radial gradient centered near
  the known case.
- `red_ring_rot`: now shows a visibly irregular, non-radially-symmetric
  blob -- land cover/terrain modulation is clearly shaping the footprint,
  not just distance decay.

This is a visualization-only fix (`spread_engine.py` and the underlying
risk arrays are unchanged) -- no modeling-behavior verification needed
beyond confirming the two preview PNGs regenerated correctly.
