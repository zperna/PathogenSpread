# Feature contract: point-feature export of the per-tree outputs

## Problem
The per-tree outputs (`run_real_site_tree_risk.py`,
`run_real_site_tree_spread.py`) exist only as CSV and matplotlib PNG. A
user cannot view them in ArcGIS Pro next to the existing rasters, and
cannot use standard GIS overlay tools (parcels, zoning) on them.

A rasterized version was considered and rejected -- see the discussion
that led to this contract. Interpolating between discrete host-tree
points invents risk values for ground with no host tree at all, which
contradicts why `compute_risk_raster` deliberately excludes host data in
the first place (`docs/feature_contracts/real_site_risk_raster.md`).

## Goal
Export the already-verified per-tree CSVs as point shapefiles in the
same CRS as the site rasters (EPSG:32610), so they can be added to
`PathogenProject.aprx` directly and rendered with graduated or
categorical symbology, with zero interpolation.

## Scope
1. **`PathogenPy/shapefile_writer.py`, new.** Stdlib `.shp` + `.shx` +
   `.dbf` + `.prj` (+ `.cpg`) writer, points only. Mirrors
   `shapefile_reader.py`'s format knowledge, written instead of read.
   No arcpy, no new dependency -- same Option B precedent as
   `docs/feature_contracts/site_tree_host_inventory.md`.
2. **`PathogenPy/export_tree_points.py`, new.** Reads the six existing
   CSVs (3 pathogens x risk + spread) already on disk under `outputs/`
   and writes one point shapefile per CSV to `outputs/gis/`. Pure format
   conversion -- it does not call `compute_risk` or `simulate_spread`,
   so it cannot silently drift from the numbers those scripts already
   produced and verified.
3. **DBF field-name crosswalk.** dBASE field names are capped at 10
   characters. Long column names (`dispersal_score`,
   `environmental_match`, `stress_amplification`, `infected_at_step`,
   `risk_at_infection`, `is_initial_case`) need abbreviations. Fixed in
   the design note and documented so a viewer in Pro can map them back.
4. **`.prj`.** A fixed WKT string for EPSG:32610 (WGS 1984 UTM Zone
   10N), the same CRS every site raster and the POS-derived inventory
   already use. Written verbatim, not derived.

## Inputs
- `outputs/<pathogen>_site_tree_risk.csv` and
  `outputs/<pathogen>_site_tree_spread.csv` for `red_ring_rot`,
  `phytophthora`, `anthracnose` -- six files, already produced by
  `run_real_site_tree_risk.py` / `run_real_site_tree_spread.py`.

## Outputs
- `PathogenPy/shapefile_writer.py`, `PathogenPy/export_tree_points.py`.
- `outputs/gis/<pathogen>_site_tree_risk.{shp,shx,dbf,prj,cpg}` and
  `outputs/gis/<pathogen>_site_tree_spread.{shp,shx,dbf,prj,cpg}` --
  six point layers.
- This contract and a design note.

## Success criteria
1. Every written shapefile round-trips through
   `shapefile_reader.read_point_shapefile`: identical `x`/`y` and
   attribute values (numeric fields compared within DBF's fixed-decimal
   rounding).
2. `.prj` matches the standard EPSG:32610 WKT string byte for byte.
3. No interpolation. Every point in the output corresponds to exactly
   one row in the source CSV -- no new geometry, no new value.
4. No new dependency, no arcpy import in either new module.
5. The field-name crosswalk is documented in the design note and as a
   comment in `export_tree_points.py`.

## Non-goals
1. Not a geodatabase feature class. Stays a shapefile; the user adds it
   to `PathogenProject.aprx` manually (Add Data, or drag-and-drop).
2. Does not re-run `compute_risk` or `simulate_spread` -- pure format
   conversion from already-verified CSVs.
3. Does not verify an actual open in ArcGIS Pro -- no arcpy is available
   in this environment. The round-trip-through-our-own-reader check plus
   the fixed `.prj` string is what this environment can verify; an
   open-in-Pro smoke test by the user is recommended but not run here.
4. Does not touch the raster outputs, `import_risk_raster.py`, or the
   arcpy export step.
5. Does not export the known-case source points as a separate layer --
   scope is exactly the two existing CSVs per pathogen. The spread CSV
   already includes the initial cases (`is_initial_case` column); the
   risk CSV does not, unchanged from what `run_real_site_tree_risk.py`
   already writes.

## Definition of done
1. This contract exists (done).
2. Design note fixes the field-name crosswalk and the `.prj` string
   (done, `docs/notes/tree_point_export.md`).
3. `shapefile_writer.py` and `export_tree_points.py` exist and run in
   the plain `.venv` (done).
4. Six shapefiles written under `outputs/gis/` (done).
5. Verification recorded below (done, 2026-09-11).

## Verification (2026-09-11)

### Round-trip through `shapefile_reader.py` -- PASS, all six files
| file | rows |
|---|---|
| red_ring_rot_site_tree_risk | 2,147 |
| red_ring_rot_site_tree_spread | 2,148 |
| phytophthora_site_tree_risk | 1,084 |
| phytophthora_site_tree_spread | 1,085 |
| anthracnose_site_tree_risk | 2,330 |
| anthracnose_site_tree_spread | 2,332 |

Every row's `x`/`y` (exact) and every attribute (numeric within 1e-5,
booleans and text exact, missing values recovered as blank) matched the
source CSV. Spread counts are one more than the risk counts because the
spread CSV includes the initial known case(s); the risk CSV does not
(unchanged, non-goal 5).

### Independent binary checks beyond the round-trip
The round-trip above only exercises `.shp` and `.dbf`, since
`shapefile_reader.py` reads `.shp` sequentially and never opens `.shx`.
Two more checks were run directly against the file bytes, because a
real GIS client (unlike this project's own reader) does use `.shx`:
1. **`.shx` / `.shp` cross-check**: for every record in every file, the
   `.shx` offset points at the matching `.shp` record header (right
   record number, right content length, shape type `1`), and both
   files' header-declared lengths match their actual size on disk.
   All six files pass.
2. **`.dbf` internal check**: declared header length, record length,
   and record count are consistent with the file's actual size, the
   field-descriptor terminator and end-of-file marker are present.
   All six files pass.

### `.prj`
All six `.prj` files match the `EPSG_32610_WKT` string in
`shapefile_writer.py` byte for byte.

### ArcGIS Pro read, via arcpy directly (2026-09-11, superseding non-goal 3)
arcpy became available in this environment after the checks above were
written. Ran a read-only script (`arcpy.Describe`,
`arcpy.management.GetCount`, `arcpy.da.SearchCursor`) against all six
files -- no write to `PathogenProject.aprx`/`.gdb`, so no risk of the
project's known schema-lock-on-open-map or headless-`aprx.save()`
issues (both are about writing into the live project, not about
reading a standalone shapefile). All six: PASS.
- Spatial reference reads as `WGS_1984_UTM_Zone_10N` (factory code
  32610) directly from the `.prj` -- no manual CRS assignment needed.
- Feature counts match the CSV row counts exactly.
- Each shapefile's extent falls inside its site's AOI box, and overlaps
  the matching `outputs/<pathogen>_site_risk.tif` -- confirms the whole
  chain (POS reprojection, AOI clip, shapefile write) lines up
  spatially with the existing raster, not just with itself.
- Field values spot-checked (species, DBH, risk components, known-case
  codes `PsMe`/`ChLa`/`PlHi` passing through unmodified) all read
  correctly.
- One cosmetic-only shapefile-format quirk, not a bug: a blank/NA
  numeric field (`DBH_IN` on known-case rows, which have no diameter)
  is confirmed still written as blank bytes in the `.dbf` (checked
  directly), but arcpy's shapefile driver displays a blank numeric
  field as `0.0` rather than `<Null>` in a cursor -- a known limitation
  of the shapefile format's numeric-null handling, not something this
  writer can change. Symbology and analysis on `RISK_SCORE`/`RISK_INF`
  (the fields that matter for this feature) are unaffected -- those are
  never blank on a host row.

### Addendum (2026-09-11): known-case export
The "natural next step" named in the design note's update summary is
now built: `export_tree_points.py` also reads each site's
`known_cases.csv` and writes `outputs/gis/<pathogen>_known_cases.shp`
(`TREE_ID`, `SPECIES` unconverted, `STRESS_IDX`, `INFECTED`). Same
writer, same `.prj`, no new module.

Verified the same way as the rest of this contract:
- Round-trip through `shapefile_reader.py`: PASS for all three
  (`red_ring_rot` 1, `phytophthora` 1, `anthracnose` 2 points) -- after
  fixing a test-script bug, not a writer bug: `pandas.read_csv` infers
  `phytophthora`'s numeric-looking `tree_id` ("1") as an integer, which
  then fails a naive string comparison against the shapefile's text
  field. Forcing `dtype={"tree_id": str}` on read fixed the check; the
  shapefile itself was correct throughout.
- arcpy read, all three: correct `WGS_1984_UTM_Zone_10N` SR, correct
  count, coordinates and `TREE_ID`/`SPECIES`/`INFECTED` match
  `known_cases.csv` exactly. `STRESS_IDX` shows `0.0` for the two sites
  where it is blank in the source CSV -- the same shapefile
  numeric-null-as-zero display quirk already recorded above, not a new
  issue.
  never blank on a host row.
