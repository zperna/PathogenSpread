# Feature contract: point-feature export of the per-tree outputs

## Problem
The per-tree outputs (`run_real_site_tree_risk.py`, `run_real_site_tree_spread.py`) exist only as CSV and matplotlib PNG. A user cannot view them in ArcGIS Pro next to the existing rasters. A user also cannot run standard GIS overlay tools (parcels, zoning) on them.

A rasterized version was considered and rejected. See the discussion that led to this contract. Interpolating between discrete host-tree points invents risk values for ground with no host tree at all. This contradicts the reason `compute_risk_raster` leaves out host data on purpose (`docs/feature_contracts/real_site_risk_raster.md`).

## Goal
Export the already verified per-tree CSVs as point shapefiles. Use the same CRS as the site rasters (EPSG:32610). The user can then add them to `PathogenProject.aprx` directly. They can render them with graduated or categorical symbology. No interpolation is done.

## Scope
1. **`PathogenPy/shapefile_writer.py`, new.** A stdlib `.shp` + `.shx` + `.dbf` + `.prj` (+ `.cpg`) writer, points only. It mirrors the format knowledge in `shapefile_reader.py`, but in the write direction. No arcpy. No new dependency. This is the same Option B approach as `docs/feature_contracts/site_tree_host_inventory.md`.
2. **`PathogenPy/export_tree_points.py`, new.** Reads the six existing CSVs (3 pathogens x risk and spread) already on disk under `outputs/`. Writes one point shapefile per CSV to `outputs/gis/`. This is a pure format conversion. It does not call `compute_risk` or `simulate_spread`. So it cannot drift from the numbers those scripts already produced and verified.
3. **DBF field-name crosswalk.** dBASE field names are capped at 10 characters. Long column names need abbreviations. These are `dispersal_score`, `environmental_match`, `stress_amplification`, `infected_at_step`, `risk_at_infection`, and `is_initial_case`. The design note fixes the crosswalk and documents it, so a viewer in Pro can map each field back to its CSV column.
4. **`.prj`.** A fixed WKT string for EPSG:32610 (WGS 1984 UTM Zone 10N). This is the same CRS that every site raster and the POS-derived inventory already use. It is written verbatim. It is not derived.

## Inputs
- `outputs/<pathogen>_site_tree_risk.csv` and `outputs/<pathogen>_site_tree_spread.csv` for `red_ring_rot`, `phytophthora`, and `anthracnose`. That is six files. They are already produced by `run_real_site_tree_risk.py` and `run_real_site_tree_spread.py`.

## Outputs
- `PathogenPy/shapefile_writer.py` and `PathogenPy/export_tree_points.py`.
- `outputs/gis/<pathogen>_site_tree_risk.{shp,shx,dbf,prj,cpg}` and `outputs/gis/<pathogen>_site_tree_spread.{shp,shx,dbf,prj,cpg}`. That is six point layers.
- This contract and a design note.

## Success criteria
1. Every written shapefile round-trips through `shapefile_reader.read_point_shapefile`. The `x` and `y` values match, and so do the attribute values. Numeric fields are compared within DBF's fixed-decimal rounding.
2. `.prj` matches the standard EPSG:32610 WKT string byte for byte.
3. No interpolation. Every point in the output corresponds to exactly one row in the source CSV. No new geometry and no new value is created.
4. No new dependency. No arcpy import in either new module.
5. The field-name crosswalk is documented in the design note and as a comment in `export_tree_points.py`.

## Non-goals
1. Not a geodatabase feature class. It stays a shapefile. The user adds it to `PathogenProject.aprx` by hand (Add Data, or drag and drop).
2. Does not re-run `compute_risk` or `simulate_spread`. It is a pure format conversion from CSVs that are already verified.
3. Does not verify an actual open in ArcGIS Pro. No arcpy is available in this environment. The round-trip check through our own reader, plus the fixed `.prj` string, is what this environment can verify. An open-in-Pro smoke test by the user is recommended. It is not run here.
4. Does not touch the raster outputs, `import_risk_raster.py`, or the arcpy export step.
5. Does not export the known-case source points as a separate layer. The scope is exactly the two existing CSVs per pathogen. The spread CSV already includes the initial cases (`is_initial_case` column). The risk CSV does not. This is unchanged from what `run_real_site_tree_risk.py` already writes.

## Definition of done
1. This contract exists (done).
2. The design note fixes the field-name crosswalk and the `.prj` string (done, `docs/notes/tree_point_export.md`).
3. `shapefile_writer.py` and `export_tree_points.py` exist and run in the plain `.venv` (done).
4. Six shapefiles are written under `outputs/gis/` (done).
5. Verification recorded below (done, 2026-09-11).

## Verification (2026-09-11)

### Round-trip through `shapefile_reader.py`: PASS, all six files
| file | rows |
|---|---|
| red_ring_rot_site_tree_risk | 2,147 |
| red_ring_rot_site_tree_spread | 2,148 |
| phytophthora_site_tree_risk | 1,084 |
| phytophthora_site_tree_spread | 1,085 |
| anthracnose_site_tree_risk | 2,330 |
| anthracnose_site_tree_spread | 2,332 |

Every row's `x`/`y` match the source exactly. Every attribute matches too. Numeric values match within 1e-5. Booleans and text match exactly. Missing values are recovered as blank.

Spread counts are one more than the risk counts. The spread CSV includes the initial known case or cases. The risk CSV does not. This is unchanged (non-goal 5).

### Independent binary checks beyond the round-trip
The round-trip above only exercises `.shp` and `.dbf`. `shapefile_reader.py` reads `.shp` in order and never opens `.shx`. Two more checks ran directly on the file bytes. A real GIS client does use `.shx`, so these checks matter.
1. **`.shx` / `.shp` cross-check.** For every record in every file, the `.shx` offset points at the matching `.shp` record header. The record number, content length, and shape type (`1`) all match. Both files' header-declared lengths match their actual size on disk. All six files pass.
2. **`.dbf` internal check.** The declared header length, record length, and record count are consistent with the file's actual size. The field-descriptor terminator and the end-of-file marker are present. All six files pass.

### `.prj`
All six `.prj` files match the `EPSG_32610_WKT` string in `shapefile_writer.py` byte for byte.

### ArcGIS Pro read, via arcpy directly (2026-09-11, superseding non-goal 3)
arcpy became available in this environment after the checks above were written. A read-only script ran against all six files. It used `arcpy.Describe`, `arcpy.management.GetCount`, and `arcpy.da.SearchCursor`. It did not write to `PathogenProject.aprx` or its `.gdb`. So the project's known problems do not apply. Those problems are the schema lock on an open map and headless `aprx.save()`. Both affect writes into the live project. They do not affect reads of a standalone shapefile. All six files pass.
- The spatial reference reads as `WGS_1984_UTM_Zone_10N` (factory code 32610) directly from the `.prj`. No manual CRS assignment is needed.
- Feature counts match the CSV row counts exactly.
- Each shapefile's extent falls inside its site's AOI box. It overlaps the matching `outputs/<pathogen>_site_risk.tif`. This confirms the whole chain (POS reprojection, AOI clip, shapefile write) lines up spatially with the existing raster. It is not only consistent with itself.
- Field values were spot-checked. Species, DBH, risk components, and known-case codes (`PsMe`/`ChLa`/`PlHi`) pass through unmodified. All read correctly.
- One cosmetic quirk, which is a shapefile format limit and not a bug. A blank numeric field (`DBH_IN` on known-case rows, which have no diameter) is still written as blank bytes in the `.dbf`. I checked this directly. But arcpy's shapefile driver shows a blank numeric field as `0.0`, not `<Null>`, in a cursor. This is a known limitation of how the shapefile format stores numeric nulls. This writer cannot change it. Symbology and analysis on `RISK_SCORE` and `RISK_INF` are not affected. Those fields are never blank on a host row.

### Addendum (2026-09-11): known-case export
The "natural next step" named in the design note's update summary is now built. `export_tree_points.py` also reads each site's `known_cases.csv`. It writes `outputs/gis/<pathogen>_known_cases.shp` (`TREE_ID`/`SPECIES`/`STRESS_IDX`/`INFECTED`). It uses the same writer and the same `.prj`. No new module was added.

Verified the same way as the rest of this contract.
- Round-trip through `shapefile_reader.py`: PASS for all three (`red_ring_rot` 1 point, `phytophthora` 1, `anthracnose` 2). This needed a fix to a test script, not to the writer. `pandas.read_csv` read `phytophthora`'s numeric-looking `tree_id` ("1") as an integer. A naive string comparison then failed against the shapefile's text field. Setting `dtype={"tree_id": str}` on read fixed the check. The shapefile was correct throughout.
- arcpy read, all three: the SR is `WGS_1984_UTM_Zone_10N`, which is correct. The count is correct. Coordinates and `TREE_ID`/`SPECIES`/`INFECTED` match `known_cases.csv` exactly. `STRESS_IDX` shows `0.0` for the two sites where it is blank in the source CSV. This is the same numeric-null-as-zero display quirk noted above. It is not a new issue.
