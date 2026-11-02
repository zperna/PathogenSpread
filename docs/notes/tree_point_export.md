# Design note: point-feature export of the per-tree outputs

Companion to `docs/feature_contracts/tree_point_export.md`.

## Field-name crosswalk

dBASE field names are capped at 10 characters. Both CSVs keep their column order. Only the name changes on write. This table is the single source of truth. A copy is also placed as a comment in `export_tree_points.py`.

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

`x`/`y` are not attribute fields. They become the point geometry, which is the normal shapefile convention. `western_hemlock` is 15 characters. `SPECIES` is sized 16 to leave margin. A blank (space-filled) numeric field is how missing data is written. Examples are `dbh_in` for source rows, and `INF_STEP` / `RISK_INF` for never-infected trees. This is the standard DBF null convention. ArcGIS reads it as `<Null>`.

## `shapefile_writer.py`

This module mirrors the format knowledge in `shapefile_reader.py`, in the write direction.

- `write_point_shapefile(path_stem, records, field_spec)`.
  - `records`: list of dicts. Each dict is `{"x": float, "y": float, **attrs}`.
  - `field_spec`: list of `(dbf_name, dbf_type, length, decimals)`. Example: `("RISK_SCORE", "N", 10, 6)`. `dbf_type` is `"C"`, `"N"`, or `"L"`.
- `.shp`: a 100-byte header. It holds the file code `9994`, the file length in 16-bit words, the version `1000`, the shape type `1`, and a bounding box equal to the min and max of all `x` and `y`. Then, for each record, there is an 8-byte big-endian record header (record number, content length `= 10` words). Then come 20 bytes of content: shape type `1`, then little-endian `x` and `y`.
- `.shx`: the same 100-byte header. Then one 8-byte pair (offset, content length) per record. The offsets are computed while `.shp` is written.
- `.dbf`: a 32-byte file header (version `0x03`, record count, header length, record length). Then one 32-byte field descriptor for each entry in `field_spec`. Then a `0x0D` terminator. Then one record per point. Each record has a leading space, which means not deleted. Each field is formatted to its fixed width:
  - `C`: left-justified and space-padded.
  - `N`: right-justified, with the given decimals. Blank-filled if the value is `None`/NaN/NA.
  - `L`: a single `T` or `F`. Blank if `None`.
- `.prj`: the fixed EPSG:32610 WKT string (below). It is written as-is on every call. This project only ever writes one CRS.
- `.cpg`: `"UTF-8"`. This matches the convention in `data/POS_Trees_Master/POS_Trees_Master.cpg`. Every value written here is plain ASCII anyway.

The EPSG:32610 WKT below goes into every `.prj`. It is quoted verbatim, not derived. It is the same CRS that `arcpy.SpatialReference(32610)` already uses throughout `export_site_layers.py`:
```
PROJCS["WGS_1984_UTM_Zone_10N",GEOGCS["GCS_WGS_1984",DATUM["D_WGS_1984",
SPHEROID["WGS_1984",6378137.0,298.257223563]],PRIMEM["Greenwich",0.0],
UNIT["Degree",0.0174532925199433]],PROJECTION["Transverse_Mercator"],
PARAMETER["False_Easting",500000.0],PARAMETER["False_Northing",0.0],
PARAMETER["Central_Meridian",-123.0],PARAMETER["Scale_Factor",0.9996],
PARAMETER["Latitude_Of_Origin",0.0],UNIT["Meter",1.0]]
```

## `export_tree_points.py`

- `PATHOGENS_AND_KINDS = [("red_ring_rot", ...), ("phytophthora", ...), ("anthracnose", ...)] x ["risk", "spread"]`. That makes six `(csv_path, field_spec, shp_path)` jobs.
- Per job:
  1. Read the CSV with `pandas`.
  2. Rename the columns per the crosswalk.
  3. Convert `bool` columns to the writer's `L` convention.
  4. Write with `shapefile_writer.write_point_shapefile`.
- The output directory is `outputs/gis/`. It is created if missing. It is a separate folder from the plotting outputs. The idea is the same as `data/<site>/gis_reference/` in `export_site_layers.py`.
- Plain `.venv`. No arcpy import.

## Assumptions

1. `x`/`y` in every source CSV are already EPSG:32610 meters. This is true for both CSVs. They come from `build_host_inventory` (POS points, already reprojected) and from `known_cases.csv` (already UTM 10N). No transform is needed here.
2. The DBF 10-character field cap is the binding constraint. Shapefile limits on the number of fields or the record length are not. Both CSVs have few enough columns that this is not an issue.
3. A round-trip through `shapefile_reader.py` is the strongest check available without arcpy. It confirms that the writer and reader agree with each other. It does not confirm that ArcGIS Pro's shapefile driver agrees with both. This is flagged as a non-goal, with a recommended manual check.

## Verification plan

1. Write all six shapefiles. Read each one back with `shapefile_reader.read_point_shapefile`. Compare it row by row against the source CSV. `x`/`y` must match exactly. They pass through unchanged in a wider datatype. Numeric fields must match within `1e-6` (the fixed 6-decimal DBF format). Booleans and `tree_id`/`species` must match exactly. Missing values are recovered as blank or empty.
2. Byte-compare the written `.prj` against the WKT string above.
3. Report record counts per file against the source CSV row counts.
4. State plainly that no ArcGIS Pro open was tested in this environment. Suggest that the user do one open-in-Pro check.

## Update summary (2026-09-11)

- The contract and this design note are written. The field crosswalk and the `.prj` are fixed above.
- Implemented `shapefile_writer.py` and `export_tree_points.py`. Ran once. This produced all six shapefiles under `outputs/gis/`.
- Full verification is in the contract's "Verification (2026-09-11)" section. The round-trip passed for all six. Two binary checks cover what the round-trip does not: the `.shx`/`.shp` cross-check and the `.dbf` internal-length check. A byte-exact `.prj` check also passed. No actual ArcGIS Pro open was tested (no arcpy here). A manual open in Pro is recommended as a follow-up.
- **Update 2026-09-11**: The known-case export named above is now built. `export_tree_points.py` also writes `outputs/gis/<pathogen>_known_cases.shp` for each site (`TREE_ID`/`SPECIES`/`STRESS_IDX`/`INFECTED`). It reuses `shapefile_writer.py` unchanged. This was verified the same way as the rest of this feature. See the contract's addendum. No items remain open.
