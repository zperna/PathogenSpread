# Design note: Real-site risk raster

## Approach
Split the pipeline at the arcpy boundary. Do not add arcpy as a dependency of the engine.

1. **`PathogenPy/arcpy_export/export_site_layers.py`**: Run once, or re-run when the .gdb changes. Run it under ArcGIS Pro's Python (`...\ArcGIS\Pro\bin\Python\envs\arcgispro-py3\python.exe`). The script reads the real sources. It reprojects everything to a shared meters CRS. It clips to a 2 km AOI around the known case. It writes flat files: numpy arrays for each surface, a `grid_meta.json` that describes the grid's real-world origin and resolution, and `known_cases.csv` for point data. No arcpy-specific objects leave this script.
2. **The existing `.venv` engine** reads only those flat files. It never touches arcpy, rasterio, or any CRS object. It needs only an `(origin_x, origin_y, resolution_m)` anchor. It does not assume the grid starts at `(0, 0)`, as the synthetic surfaces do.
3. **`PathogenPy/arcpy_export/import_risk_raster.py`**: Run under arcpy again, after the engine produces a risk array. It writes the array back out as a real georeferenced GeoTIFF. It uses the same origin, resolution, and CRS recorded in `grid_meta.json`.

## Design choices

### CRS and units
The source layers use three different CRSs:
- The point and NLCD use Oregon Lambert feet.
- gNATSGO uses Albers CONUS meters.
- The DEM image service uses a geographic or Web-Mercator-like CRS.

The engine's dispersal constants are defined in meters. Rather than teach the engine to handle units or CRS, the export script resolves this once. It reprojects everything to UTM Zone 10N (EPSG:32610, meters) at export time. The engine sees only meters. This matches how the synthetic prototype already worked.

### Grid representation stays simple
`spread_engine.py`'s existing raster sampling (`_sample_grid_at_points`) indexes a square grid by dividing local coordinates by `area_size_m`. Rather than rewrite this to carry a full affine transform, the export script does two things:
- It makes every layer share one CRS, one resolution, and one aligned extent.
- It records the grid's real-world lower-left corner as `origin_x`/`origin_y` in `grid_meta.json`.

The engine change is additive. Sampling subtracts the origin before the existing divide-by-`area_size_m` math. `origin_x`/`origin_y` default to `0`. So all existing synthetic-data code paths and tests are unaffected.

### Soil: raster and table join, not a raw raster
`MapunitRaster_10m` stores only a `MUKEY` code per cell. It does not store a usable suitability value. The export script joins each cell's `MUKEY` to `muaggatt.drclassdcd` (the 7-class USDA dominant drainage class). It writes an integer class-code raster and a small crosswalk.

`spatial_inputs.py` turns the 7 classes into a 0-1 suitability score. It uses an ordinal mapping. Wetter means more favorable for this fungal pathogen. This is consistent with the placeholder soil scoring it replaces:

    Excessively drained        -> 0.15
    Somewhat excessively drained -> 0.25
    Well drained                -> 0.35
    Moderately well drained     -> 0.55
    Somewhat poorly drained     -> 0.75
    Poorly drained              -> 0.90
    Very poorly drained         -> 1.00

### Terrain: derive locally, do not depend on a live service
The DEM exists only as a live ODF Image Service in the current Pro project. It also has an ephemeral Temp-folder raster-function cache that will get cleaned up. The export script pulls a permanent local DEM clip for the AOI once. Then it runs `arcpy.sa.Slope` and `arcpy.sa.Aspect` on that local copy.

Terrain suitability is a simple, explicitly labeled placeholder. Moderate slope scores higher, because it retains more moisture than very steep, better-drained slopes. North-facing aspect (cooler, damper) also scores higher. This is a documented domain assumption. It is not validated pathology.

### Raster risk mode is new
`compute_risk` (point-based) assumes each row has a `species` and a `stress_index`. A raster cell has no equivalent. Rather than stretch those semantics, this design adds `compute_risk_raster()`. It uses the same dispersal kernel and environmental-match logic. It applies them to every grid cell instead of every tree row.

Host susceptibility and stress amplification are left out. They are documented as out of scope (see the contract's Non-goals). This keeps the existing `compute_risk` untouched. The Douglas-fir grove synthetic prototype still works exactly as before.

## Assumptions
- A 2 km AOI around the known case is large enough to show the dispersal kernel's falloff (150 m max). It gives useful surrounding context. It is small enough to keep the export fast.
- ~~30 m output resolution (matching native NLCD) is an acceptable common grid resolution, even though gNATSGO is natively 10 m and the DEM is ~10 m: those get resampled down at export.~~ Superseded 2026-08-09: bumped to 10 m (matching gNATSGO and DEM native resolution) so the 150 m dispersal kernel resolves across about 15 cells instead of about 5. NLCD is now the layer that gets resampled (nearest-neighbor upsampled), not the other way around. See the contract's Resolution addendum.
- Moisture and temperature spatial weights are unused this iteration. There is no real climate layer yet. The existing renormalize-over-available-surfaces behavior in `_combine_spatial_environment` handles this. No engine changes are needed.

## Expected outcome
A GeoTIFF centered on the known Douglas-fir case. It shows a ring of elevated risk near the point. The risk fades within about 150 m. Land cover, soil drainage, and terrain modulate the pattern. The file is suitable for loading back into `PathogenProject.aprx` as a layer you can check.

## Verification

Ran end to end against the real data on 2026-08-08:

- `export_site_layers.py` (ArcGIS Pro Python) exported a 67x67 cell, 30 m grid. The grid is centered on the one `RedRingRot` known case (Douglas-fir / `PsMe`). It wrote the grid to `data/site/`. It also wrote reference GeoTIFFs to `data/site/gis_reference/`.
- `run_real_site_risk_raster.py` (`.venv`) computed the risk raster. The range is 0.000-0.310. The mean is 0.001. The peak is at the known case's cell. It saved `outputs/red_ring_rot_site_risk.npy` and a preview PNG. The preview shows a tight hotspot at the known point. The hotspot fades well within the AOI. This is consistent with `red_ring_rot`'s 150 m `max_dispersal_distance_m`.
- `import_risk_raster.py` (ArcGIS Pro Python) converted that array back to `outputs/red_ring_rot_site_risk.tif` (EPSG:32610). The georeferencing round trip is confirmed. Sampling the GeoTIFF at the known case's real UTM coordinate (`GetCellValue`) returned 0.310. This is the same peak value computed in the engine, at the same real-world location as the original `RedRingRot` point. All three of the contract's success criteria are met.
- Regression check: both existing synthetic prototypes (`run_prototype.py`, `run_red_ring_rot_grove.py`) still run unchanged. They produce the same kind of output as before. The grid-origin and raster sampling changes in `spread_engine.py` did not affect the synthetic (origin `0,0`) code path.

### Problems hit and fixed along the way
- **AOI clipping silently did nothing.** The `arcpy.Extent` built for the AOI had no coordinate system attached. Depending on the environment-setting order, ArcGIS misread the meter-based bounds. It then processed the *entire* NLCD raster (27,665 x 30,643 cells) instead of the 2 km AOI. The fix attaches `spatial_reference=TARGET_SR` directly to the `Extent` object at construction. The fix does not rely on `arcpy.env.outputCoordinateSystem` alone.
- **DEM clip hung indefinitely.** `arcpy.management.Clip` against the live ODF `ImageServer` URL took about 4 seconds in isolation. Inside the full script, it hung for over an hour. The root cause was leftover `arcpy.env.extent`, `outputCoordinateSystem`, and `cellSize` values from the land cover and soil steps. Those values used a different CRS and extent than the DEM service's own. The fix resets those three environment settings to `None` right before the live-service `Clip` call.
- **Cross-CRS pixel misalignment.** Reprojecting land cover (from Oregon Lambert feet) gave a slightly different pixel grid (73x72). Soil and terrain (from Albers/feet DEM, both 67x67) gave 67x67 for the same requested extent. This is an expected side effect of reprojecting between CRSs with no explicit snap raster. For this prototype, the fix crops all layers to their common origin-aligned shape. It does not chase exact ArcGIS pixel snapping. The crop point is logged, not silent.

## Update summary
Real Oregon data now flows through the existing engine. The inputs are NLCD land cover, gNATSGO soil drainage, slope and aspect from the ODF DEM, and the one confirmed red ring rot case. They run through a new raster-risk mode. The output is a GeoTIFF that opens correctly in `PathogenProject.aprx`. The synthetic Douglas-fir grove prototype is unchanged and still works.

Next iteration candidates:
- A real field tree inventory. This re-enables host susceptibility, stress amplification, and per-tree scoring.
- Real moisture and temperature layers.
- Replacing the placeholder slope, aspect, and drainage-class scoring with values based on actual forest pathology guidance, not ordinal domain judgment.

### Resolution bump to 10 m: verification (2026-08-09)
The full three-stage pipeline ran again (`export_site_layers.py`, then `run_real_site_risk_raster.py`, then `import_risk_raster.py`). The change was `CELL_SIZE_M` going from 30 to 10 in `export_site_layers.py`. Both sites now export 200x200 cell grids, up from 67x67. The origin-corner pixel-alignment crop still triggers as expected. Land cover lands a few cells off from soil and terrain because of cross-CRS reprojection, as before. The crop is logged.

- `red_ring_rot`: risk range 0.000-0.472 (was 0.000-0.310 at 30 m). Mean 0.001. The peak is still at the known case's cell. The higher peak is expected, not a regression. At 30 m, the known-case cell's environmental suitability was averaged or resampled across a coarser footprint. At 10 m, it reflects a smaller, more local area right at the point.
- `phytophthora`: risk range 0.000-0.133. Mean 0.000. The peak is at the known case's cell.
- `import_risk_raster.py` round-tripped both pathogens to 10 m GeoTIFFs (`outputs/red_ring_rot_site_risk.tif`, `outputs/phytophthora_site_risk.tif`). They use the same EPSG:32610 CRS as before. No code changes were needed. Resolution is read from each run's `grid_meta.json`. It is not hardcoded.
- Regression check: `spread_engine.py`'s grid sampling and raster-risk code took no changes. Resolution was already a `grid_meta.json` parameter, not a hardcoded value. This was a data re-export plus a re-run, not an engine change.

### Preview scaling fix (2026-08-14)
The finer structure from the resolution bump was real. It was not visible in `run_real_site_risk_raster.py`'s preview PNG. The preview plotted the full 2 km AOI with a fixed 0-1 color scale shared across pathogens. Phytophthora's footprint is about 40 m wide with a 0.13 peak. It rendered as a flat, pale rectangle. That looked the same as "nothing here."

A throwaway diagnostic script showed that the raster had real, asymmetric structure. It had 16 distinct nonzero cells. The peak cell sat away from the known case's exact point location, because soil and terrain modulated the values. The shipped preview could not show this at that scale.

The fix changes `run_one()`'s plotting in two ways:
- It crops to the risk footprint. The footprint is the bounding box of nonzero cells plus the source points, padded by 10 cells.
- It sets the color range from that window's own data, not a fixed 0-1 scale. The title shows the actual peak value.

Both pathogens were re-run:
- `phytophthora`: now shows a clean, tight radial gradient centered near the known case.
- `red_ring_rot`: now shows an irregular, non-radially-symmetric blob. Land cover and terrain modulation clearly shape the footprint, not just distance decay.

This is a visualization-only fix. `spread_engine.py` and the underlying risk arrays are unchanged. No modeling-behavior verification is needed. The only check was that the two preview PNGs regenerated correctly.
