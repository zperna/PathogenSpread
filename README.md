# Pathogen Spread Risk Prototype

This project flags risk for tree health and invasive pathogen spread. The
system is explainable and extensible. Pathogen behavior (dispersal kernel,
host susceptibility, environmental triggers) is stored in config
dictionaries. It is not hard-coded. You can add new pathogens or data
sources without changes to the core engine.

**Status:** prototype scaffold. This is not a validated predictive model.
The scores, spatial weights, terrain and soil suitability mappings, and
spread-simulation thresholds are domain-judgment placeholders. Each one is
documented. Read the caveats in `pathogens.py` and `docs/notes/`.

## How it works

`PathogenPy/spread_engine.py` is a generic spread-risk engine. It takes
these inputs:
- A tree inventory (pandas DataFrame) **or** a raster grid of environmental
  surfaces.
- A pathogen config from `PathogenPy/pathogens.py`. The config holds the
  dispersal kernel, host susceptibility, environmental triggers, spatial
  weights, and spread-step threshold.
- Optional environmental surfaces: land cover, soil drainage and water
  attributes, terrain, wetness, and wind exposure.
- Optional site wind data (prevailing direction and directionality
  strength). The engine uses it only for airborne or vector-transmitted
  pathogens.

The output is an explainable 0-1 risk score. `compute_risk` gives one score
per tree. `compute_risk_raster` gives one score per grid cell. The math is
simple and you can inspect it. It uses distance-decay kernels stretched
along the prevailing wind and a weighted environmental match. It uses no
opaque models.

These features use the engine:
- **Per-tree real-site risk.** This builds a host inventory from the City
  of Eugene POS tree layer. It uses a stdlib shapefile reader, a
  closed-form CRS transform, and a species crosswalk. It then ranks host
  trees near the known cases.
- **Spread simulation** (`spread_simulation.py`). This repeats the same
  per-tree hazard over generations. The infected set grows each
  generation. The result is deterministic and illustrative. It is a what-if
  trajectory, not a forecast.
- **Tree point export.** This writes the per-tree results and known cases
  as point shapefiles. You can use them directly in ArcGIS Pro.

Configured pathogens:
- `red_ring_rot`, `phytophthora`, and `anthracnose`. Each has a real Oregon
  site.
- `emerald_ash_borer`. Config only. It has no real site because no
  confirmed case exists.

The image below shows the real-site pipeline output in
`PathogenProject.aprx`. The GeoTIFF is the Red Ring Rot risk raster over the
real parcel. The dark hotspot has its peak at the known case.

![Red Ring Rot site risk raster in ArcGIS Pro](docs/images/red_ring_rot_risk_pro_preview.png)

The image below shows a site risk raster (magenta) in ArcGIS Pro over
aerial imagery. The points are POS tree locations.

![Site risk raster with POS tree points in ArcGIS Pro](docs/images/Screenshot%202026-09-11%20115139.png)

## Repository layout

```
PathogenPy/              Engine + runnable scripts (plain .venv, no arcpy)
  spread_engine.py          Core dispersal/risk math, generic across pathogens
  spread_simulation.py      Multi-generation what-if spread on an inventory
  pathogens.py              Per-pathogen config dicts
  synthetic_data.py         Synthetic inventory/environment generators
  spatial_inputs.py         Loads real site grids, scores soil/terrain surfaces
  site_tree_inventory.py    Builds per-site host inventory from POS tree layer
  shapefile_reader.py       Stdlib point-shapefile + .dbf reader
  shapefile_writer.py       Stdlib point-shapefile writer (EPSG:32610)
  crs_transform.py          StatePlane OR South (ft) -> UTM 10N (m), stdlib math
  species_crosswalk.py      POS species strings -> engine host keys
  fetch_wind_rose.py        Nearest-station wind rose per site (IEM API)
  run_prototype.py              Synthetic multi-pathogen prototype run
  run_red_ring_rot_grove.py     Synthetic single-pathogen grove scenario
  run_real_site_risk_raster.py  Risk rasters over real site data
  run_real_site_tree_risk.py    Per-tree risk ranking over real sites
  run_real_site_tree_spread.py  Per-tree spread simulation over real sites
  export_tree_points.py         Per-tree CSVs + known cases -> point shapefiles
  arcpy_export/             Scripts that DO require arcpy (see below)
    export_site_layers.py     Exports real GIS data -> flat .npy/.json/.csv
    import_risk_raster.py     Converts computed risk arrays -> GeoTIFF

data/                    Flat, CRS-free exported site data (tracked in git)
  site/, site_phytophthora/, site_anthracnose/
                           Per-pathogen site grids, known cases, grid_meta.json,
                           wind_rose.json, gis_reference/ GeoTIFFs
  POS_Trees_Master/        City of Eugene POS tree layer (point shapefile)

outputs/                 Risk rasters, GeoTIFFs, per-tree CSVs, preview PNGs
  gis/                     Point shapefiles from export_tree_points.py
docs/                    Contract-first artifact chain (see below)
tests/                   pytest tests (grove scenario, spatial inputs)
PathogenProject/         ArcGIS Pro project: .gdb sources, NLCD raster, .aprx
                           (gitignored -- large binary GIS data, stays local)
```

## Setup

The engine (`PathogenPy/`, but not `arcpy_export/`) needs only a plain
Python environment:

```
python -m venv .venv
.venv\Scripts\activate
pip install numpy pandas matplotlib scipy pytest
```

`PathogenPy/arcpy_export/*.py` is kept separate on purpose. These scripts
need **ArcGIS Pro's own Python**, not this venv:

```
"C:\Program Files\ArcGIS\Pro\bin\Python\envs\arcgispro-py3\python.exe" export_site_layers.py
```

The plain `.venv` never imports arcpy, rasterio, or geopandas. It reads only
the flat files that `export_site_layers.py` writes to `data/`. For the same
reason, shapefile I/O and the CRS transform use only the standard library.

## Running it

**Synthetic prototypes** (no real data required):
```
python PathogenPy/run_prototype.py
python PathogenPy/run_red_ring_rot_grove.py
```

**Real-site raster pipeline** (requires `PathogenProject/` GIS data locally):
```
# 1. Export real GIS data to flat files (ArcGIS Pro Python)
"C:\Program Files\ArcGIS\Pro\bin\Python\envs\arcgispro-py3\python.exe" PathogenPy\arcpy_export\export_site_layers.py

# 2. Fetch each site's wind rose (plain .venv, needs internet)
python PathogenPy\fetch_wind_rose.py

# 3. Compute risk rasters (plain .venv)
python PathogenPy\run_real_site_risk_raster.py

# 4. Convert results back to georeferenced GeoTIFFs (ArcGIS Pro Python)
"C:\Program Files\ArcGIS\Pro\bin\Python\envs\arcgispro-py3\python.exe" PathogenPy\arcpy_export\import_risk_raster.py
```

Notes on the raster pipeline:
1. Run step 1 again when the source `.gdb` data changes. No other code
   changes are needed.
2. Run step 2 again only if a site's AOI moves.
3. `data/` is tracked in git. On a fresh clone you can skip steps 1-2.
4. To view the results, load `outputs/*.tif` into `PathogenProject.aprx`.
   Add the layers and save from the Pro UI. Do not script `aprx.save()`
   headlessly. It hangs (see `docs/notes/`).

**Real-site per-tree pipeline** (plain .venv, uses tracked `data/` only):
```
python PathogenPy\run_real_site_tree_risk.py     # ranked per-tree risk CSV + preview
python PathogenPy\run_real_site_tree_spread.py   # spread CSV, epidemic curve, frames
python PathogenPy\export_tree_points.py          # CSVs -> outputs/gis/*.shp
```

Run `export_tree_points.py` after the two run scripts. It only converts
their CSVs. Then add the `outputs/gis/` shapefiles to
`PathogenProject.aprx`. Symbolize risk layers by `RISK_SCORE`. Symbolize
spread layers by `INF_STEP`.

**Tests:**
```
pytest tests/
```

The current tests cover only the grove scenario and `spatial_inputs.py`.
These modules have no tests yet: the per-tree inventory, the spread
simulation, and the shapefile and CRS modules.

## Contract-first artifact chain

Each feature is a chain of artifacts, not only code. See `CLAUDE.md` and
`docs/artifact_chain.md`.

1. **Contract** (`docs/feature_contracts/<feature>.md`). Problem, scope,
   inputs and outputs, success criteria.
2. **Design note** (`docs/notes/<feature>.md`). Approach, assumptions,
   verification results.
3. **Implementation.** The code.
4. **Verification.** Run the code and record the result.
5. **Summary** (`docs/summaries/<feature>.md`, or the end of the design
   note). What changed and what comes next.

`docs/project_contract.md` gives the overall product goal and planned
changes. `docs/feature_contracts/` and `docs/notes/` explain specific
design choices. Examples:
- Why raster risk mode excludes host susceptibility.
- Why spatial weights differ per transmission mode.
- Why tree results export as points and not as a raster.

## Known limitations

- Each real site has only one or two confirmed cases (Red Ring Rot: 1,
  Phytophthora: 1, Anthracnose: 2). The model is not fitted or calibrated.
- The suitability scores for soil drainage class, slope and aspect, and
  moisture and temperature are ordinal placeholders. They come from domain
  judgment, not from pathology literature.
- No real moisture or temperature climate layers are connected yet.
- Wind data comes from one nearest ASOS/AWOS station per site. Willamette
  Valley winds are seasonally bimodal. A single prevailing direction is a
  simplification (see `docs/notes/real_wind_data.md`).
- Raster risk mode has no per-cell species or stress data. For this
  reason, it leaves out host susceptibility and stress amplification on
  purpose.
- The POS tree layer has no health field. Per-tree `stress_index` is a
  constant default. Species mapping is mostly at genus level.
- Spread simulation generations are abstract dispersal cycles. They are
  not seasons or years. `promotion_threshold` is not calibrated.
