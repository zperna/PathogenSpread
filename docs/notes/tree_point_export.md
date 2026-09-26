# Design note: point-feature export of the per-tree outputs

Companion to `docs/feature_contracts/tree_point_export.md`.

## Field-name crosswalk

dBASE field names are capped at 10 characters. Both CSVs keep their
column order; only the name changes on write. This table is the single
source of truth -- also placed as a comment in `export_tree_points.py`.

### `<pathogen>_site_tree_risk.csv` -> `_risk.dbf`
| CSV column | DBF field | Type |
|---|---|---|
| `tree_id` | `TREE_ID` | C(15) |
| `species` | `SPECIES` | C(16) |
| `dbh_in` | `DBH_IN` | N(6,1) |
| `risk_score` | `RISK_SCORE` | N(10,6) |
| `dispersal_score` | `DISP_SCORE` | N(10,6) |
| `susceptibility` | `SUSCEPT` | N(10,6) |
| `environmental_match` | `ENV_MATCH` | N(10,6) |
| `stress_amplification` | `STRESS_AMP` | N(10,6) |

### `<pathogen>_site_tree_spread.csv` -> `_spread.dbf`
| CSV column | DBF field | Type |
|---|---|---|
| `tree_id` | `TREE_ID` | C(15) |
| `species` | `SPECIES` | C(16) |
| `dbh_in` | `DBH_IN` | N(6,1) |
| `is_initial_case` | `INIT_CASE` | L |
| `infected_at_step` | `INF_STEP` | N(3,0) |
| `risk_at_infection` | `RISK_INF` | N(10,6) |
| `infected` | `INFECTED` | L |

`x`/`y` are not attribute fields -- they become the point geometry, the
normal shapefile convention. `western_hemlock` is 15 characters, so
`SPECIES` is sized 16 for margin. A blank (space-filled) numeric field
is how missing data is written (`dbh_in` for source rows, `INF_STEP` /
`RISK_INF` for never-infected trees) -- the standard DBF null
convention, read as `<Null>` by ArcGIS.

## `shapefile_writer.py`

Mirrors `shapefile_reader.py`'s format knowledge, in the write direction.

- `write_point_shapefile(path_stem, records, field_spec)`.
  - `records`: list of dicts, each `{"x": float, "y": float, **attrs}`.
  - `field_spec`: list of `(dbf_name, dbf_type, length, decimals)`,
    e.g. `("RISK_SCORE", "N", 10, 6)`. `dbf_type` is `"C"`, `"N"`, or
    `"L"`.
- `.shp`: 100-byte header (file code `9994`, file length in 16-bit
  words, version `1000`, shape type `1`, bounding box = min/max of all
  `x`/`y`) then, per record, an 8-byte big-endian record header
  (record number, content length `= 10` words) and 20 bytes of content
  (shape type `1`, then little-endian `x`, `y`).
- `.shx`: same 100-byte header, then one 8-byte (offset, content length)
  pair per record -- offsets computed while writing `.shp`.
- `.dbf`: 32-byte file header (version `0x03`, record count, header
  length, record length) then one 32-byte field descriptor per entry in
  `field_spec`, a `0x0D` terminator, then one record per point: a
  leading space (not deleted) plus each field formatted to its fixed
  width -- `C` left-justified and space-padded, `N` right-justified
  with the given decimals (blank-filled if the value is `None`/NaN/NA),
  `L` a single `T`/`F` (blank if `None`).
- `.prj`: the fixed EPSG:32610 WKT string (below), written as-is on
  every call -- this project only ever writes one CRS.
- `.cpg`: `"UTF-8"`, matching the convention seen in
  `data/POS_Trees_Master/POS_Trees_Master.cpg`, even though every value
  written here is plain ASCII.

EPSG:32610 WKT written to every `.prj` (standard, quoted verbatim, not
derived -- this is the same CRS `arcpy.SpatialReference(32610)` already
uses throughout `export_site_layers.py`):
```
PROJCS["WGS_1984_UTM_Zone_10N",GEOGCS["GCS_WGS_1984",DATUM["D_WGS_1984",
SPHEROID["WGS_1984",6378137.0,298.257223563]],PRIMEM["Greenwich",0.0],
UNIT["Degree",0.0174532925199433]],PROJECTION["Transverse_Mercator"],
PARAMETER["False_Easting",500000.0],PARAMETER["False_Northing",0.0],
PARAMETER["Central_Meridian",-123.0],PARAMETER["Scale_Factor",0.9996],
PARAMETER["Latitude_Of_Origin",0.0],UNIT["Meter",1.0]]
```

## `export_tree_points.py`

- `PATHOGENS_AND_KINDS = [("red_ring_rot", ...), ("phytophthora", ...),
  ("anthracnose", ...)] x ["risk", "spread"]` -- six `(csv_path,
  field_spec, shp_path)` jobs.
- Per job: read the CSV with `pandas`, rename columns per the crosswalk,
  convert `bool` columns to the writer's `L` convention, write via
  `shapefile_writer.write_point_shapefile`.
- Output directory `outputs/gis/`, created if missing -- a separate
  folder from the plotting outputs, same spirit as
  `data/<site>/gis_reference/` in `export_site_layers.py`.
- Plain `.venv`, no arcpy import.

## Assumptions

1. `x`/`y` in every source CSV are already EPSG:32610 meters -- true
   for both CSVs, since they come from `build_host_inventory` (POS
   points already reprojected) and `known_cases.csv` (already UTM 10N).
   No transform needed here.
2. DBF's 10-character field cap is the binding constraint, not any
   shapefile limit on the number of fields or record length -- both
   CSVs have few enough columns that this is not an issue.
3. A round-trip through `shapefile_reader.py` is the strongest check
   available without arcpy. It confirms the writer and reader agree
   with each other, not that ArcGIS Pro's shapefile driver agrees with
   both -- flagged as a non-goal, with a recommended manual check.

## Verification plan

1. Write all six shapefiles, then read each back with
   `shapefile_reader.read_point_shapefile` and compare row-for-row
   against the source CSV: `x`/`y` exact (they pass through unchanged
   in a wider datatype), numeric fields within `1e-6` (the fixed
   6-decimal DBF format), booleans and `tree_id`/`species` exact,
   missing values recovered as blank/empty.
2. Byte-compare the written `.prj` against the WKT string above.
3. Report record counts per file against the source CSV row counts.
4. State plainly that no ArcGIS Pro open was tested in this
   environment, and suggest the user do one open-in-Pro check.

## Update summary (2026-09-11)

- Contract and this design note written; field crosswalk and `.prj`
  fixed above.
- Implemented `shapefile_writer.py` and `export_tree_points.py`; ran
  once, producing all six shapefiles under `outputs/gis/`.
- Verification in full in the contract's "Verification (2026-09-11)"
  section: round-trip PASS on all six, plus two binary checks the
  round-trip alone does not cover (`.shx`/`.shp` cross-check, `.dbf`
  internal-length check), plus a byte-exact `.prj` check. No actual
  ArcGIS Pro open was tested (no arcpy here) -- recommended as a manual
  follow-up.
- **Update 2026-09-11**: the known-case export named above is now
  built. `export_tree_points.py` also writes
  `outputs/gis/<pathogen>_known_cases.shp` per site
  (`TREE_ID`/`SPECIES`/`STRESS_IDX`/`INFECTED`), reusing
  `shapefile_writer.py` unchanged. Verified the same way as the rest of
  this feature -- see the contract's addendum. Nothing left open.
