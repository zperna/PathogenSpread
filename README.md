# Pathogen Spread Risk Prototype

An explainable, extensible risk-flagging system for tree health and invasive
pathogen spread. Pathogen behavior (dispersal kernel, host susceptibility,
environmental triggers) lives entirely in config dictionaries, not
hard-coded logic, so new pathogens or data sources can be added without
touching the core engine.

**Status:** prototype scaffold. Scoring, spatial weights, and terrain/soil
suitability mappings are documented domain-judgment placeholders, not a
validated predictive model -- see the caveats in `pathogens.py` and
`docs/notes/`.

## How it works

`PathogenPy/spread_engine.py` is a generic spread-risk engine that takes:
- a tree inventory (pandas DataFrame) **or** a raster grid of environmental
  surfaces,
- a pathogen config from `PathogenPy/pathogens.py` (dispersal kernel, host
  susceptibility, environmental triggers, spatial weights),
- and optional environmental surfaces (land cover, soil drainage, terrain,
  moisture, temperature),

and produces an explainable 0-1 risk score per tree (`compute_risk`) or per
grid cell (`compute_risk_raster`). Everything is simple, inspectable math
(distance-decay kernels, weighted environmental match) -- no opaque models.

## Repository layout

```
PathogenPy/            Engine + runnable scripts (plain .venv, no arcpy)
  spread_engine.py        Core dispersal/risk math, generic across pathogens
  pathogens.py             Per-pathogen config dicts
  synthetic_data.py        Synthetic inventory/environment generators
  spatial_inputs.py        Loads real site grids, scores soil/terrain surfaces
  run_prototype.py         Synthetic multi-pathogen prototype run
  run_red_ring_rot_grove.py  Synthetic single-pathogen grove scenario
  run_real_site_risk_raster.py  Computes risk rasters over real site data
  arcpy_export/           Scripts that DO require arcpy (see below)
    export_site_layers.py   Exports real GIS data -> flat .npy/.json/.csv
    import_risk_raster.py   Converts computed risk arrays -> GeoTIFF

data/                   Flat, CRS-free exported site data (tracked in git)
  site/, site_phytophthora/   Per-pathogen site grids + known cases

outputs/                Computed risk rasters, GeoTIFFs, preview PNGs
docs/                   Contract-first artifact chain (see below)
tests/                  pytest tests for the engine/spatial inputs
PathogenProject/        ArcGIS Pro project: .gdb sources, NLCD raster, .aprx
                         (gitignored -- large binary GIS data, stays local)
```

## Setup

The engine (`PathogenPy/`, excluding `arcpy_export/`) only needs a plain
Python environment:

```
python -m venv .venv
.venv\Scripts\activate
pip install numpy pandas matplotlib scipy pytest
```

`PathogenPy/arcpy_export/*.py` is intentionally split out because it needs
**ArcGIS Pro's own Python**, not this venv:

```
"C:\Program Files\ArcGIS\Pro\bin\Python\envs\arcgispro-py3\python.exe" export_site_layers.py
```

The plain `.venv` never imports arcpy/rasterio/geopandas -- it only reads
the flat files that `export_site_layers.py` writes to `data/`.

## Running it

**Synthetic prototypes** (no real data required):
```
python PathogenPy/run_prototype.py
python PathogenPy/run_red_ring_rot_grove.py
```

**Real-site pipeline** (requires `PathogenProject/` GIS data locally):
```
# 1. Export real GIS data to flat files (ArcGIS Pro Python)
"C:\Program Files\ArcGIS\Pro\bin\Python\envs\arcgispro-py3\python.exe" PathogenPy\arcpy_export\export_site_layers.py

# 2. Compute risk rasters (plain .venv)
python PathogenPy\run_real_site_risk_raster.py

# 3. Convert results back to georeferenced GeoTIFFs (ArcGIS Pro Python)
"C:\Program Files\ArcGIS\Pro\bin\Python\envs\arcgispro-py3\python.exe" PathogenPy\arcpy_export\import_risk_raster.py
```
Re-run step 1 whenever the source `.gdb` data changes; no code changes are
needed elsewhere. Load the resulting `outputs/*.tif` into
`PathogenProject.aprx` to view (add layers + save from the Pro UI --
scripting `aprx.save()` headlessly hangs, see `docs/notes/`).

**Tests:**
```
pytest tests/
```

## Contract-first artifact chain

This project treats every feature as a chain of artifacts rather than just
code (see `CLAUDE.md` and `docs/artifact_chain.md`):

1. **Contract** (`docs/feature_contracts/<feature>.md`) -- problem, scope,
   inputs/outputs, success criteria.
2. **Design note** (`docs/notes/<feature>.md`) -- approach, assumptions,
   verification results, update summary.
3. **Implementation** -- the code.
4. **Verification** -- run it, capture the result.
5. **Summary** -- what changed, what's next.

`docs/project_contract.md` has the overall product goal and planned
evolution. Read `docs/feature_contracts/` and `docs/notes/` for the reasoning
behind specific design choices (e.g. why raster risk mode excludes host
susceptibility, why spatial weights differ per transmission mode).

## Known limitations

- Only one confirmed case exists per pathogen (Red Ring Rot, Phytophthora)
  -- this is not a fitted/calibrated model.
- Soil drainage-class, slope/aspect, and moisture/temperature suitability
  scores are ordinal domain-judgment placeholders, not sourced from
  pathology literature.
- No real moisture/temperature climate layers are wired in yet.
- Raster risk mode has no per-cell species/stress data, so host
  susceptibility and stress amplification are intentionally left out of it.
