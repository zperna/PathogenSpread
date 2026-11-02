# Feature contract: real per-tree host inventory from the Eugene tree dataset

## Problem
The real-site pipeline only runs `compute_risk_raster`. That function answers "how favorable is this location for spread from the known source(s)." It drops host susceptibility and stress amplification by design. It has no per-tree data. See `docs/feature_contracts/real_site_risk_raster.md` Non-goals.

`compute_risk` (the per-tree path) has never run on real data. It only runs on synthetic inventories in `run_prototype.py` and `run_red_ring_rot_grove.py`.

A real tree inventory now exists in the repo: `data/POS_Trees_Master/`. It is a City of Eugene Parks and Open Space tree point layer with 111,324 records. This is the "data integration" milestone in `docs/project_contract.md`.

Naming note: The dataset is the Parks and Open Space ("POS") inventory. It is not the street right-of-way tree list. Coverage is park and open-space parcels, not streets. This changes which trees fall inside each site AOI. It is a documented scope limit, not a defect.

## Goal
Turn the POS tree layer into a per-site host inventory. The existing `compute_risk` function must be able to consume it. Add a run script too. The script produces a ranked at-risk tree list and a preview map for each configured real site. Reuse the engine, the pathogen configs, and `load_site_grid` unchanged.

## Inputs
1. `data/POS_Trees_Master/POS_Trees_Master.shp` (+ `.dbf` `.shx` `.prj` `.cpg`). Point shapefile with 111,324 records.
   - CRS: NAD83(HARN) StatePlane Oregon South FIPS 3602, International Feet (per `.prj`). Sites use UTM 10N (EPSG:32610), meters. Reprojection is required.
   - The data bounding box spans roughly lat 43.976-44.135, lon -123.206 to -123.004. All three current site AOI centroids fall inside it (`site` 44.000/-123.082, `site_phytophthora` 44.088/-123.110, `site_anthracnose` 44.048/-123.079).
   - Relevant `.dbf` fields:
     - `site_typ`: `T` = tree (88,694), `S` = stump (4,975), `P` = planting site / vacant (17,655). Only `T` is a living host.
     - `Tree_speci`: `"Scientific name - common name"` in one string. 306 distinct values. `"Unknown"` on 13,267 records. Blank on 4,127. `T` rows with a real species: 86,773.
     - `diameter`: numeric DBH. Some rows hold `"***"`. It is carried through for reporting only. It is not used in risk math.
     - No condition, health, or vigor field exists. This dataset gives no basis for a per-tree `stress_index`.
2. `data/<site_name>/known_cases.csv`. Unchanged. It supplies the `infected=True` source points for each site.
3. `data/<site_name>/grid_meta.json`, the `.npy` surfaces, and `wind_rose.json`. These are already produced by `export_site_layers.py` and `fetch_wind_rose.py`. No re-export is needed.
4. `pathogens.PATHOGENS`: unchanged. `red_ring_rot`, `phytophthora`, and `anthracnose` already have both `host_susceptibility` and `spatial_weights`.

## Scope
1. Species crosswalk (`PathogenPy/species_crosswalk.py`, new):
   - A dict. It maps POS `Tree_speci` strings (or their leading genus) to the engine's `host_susceptibility` keys: `oak, maple, douglas_fir, western_hemlock, pine, sycamore, dogwood, oregon_ash, green_ash`.
   - Genus-level mapping covers most trees. `Acer` -> `maple` (17,887 trees). `Quercus` -> `oak` (11,321). `Pseudotsuga` -> `douglas_fir` (7,947). `Cornus` -> `dogwood` (1,573). `Platanus` -> `sycamore` (1,401). `Pinus` -> `pine` (3,488). `Tsuga` -> `western_hemlock` (119).
   - `Fraxinus` (8,386 trees) needs species-level handling. `Fraxinus latifolia` -> `oregon_ash`. `Fraxinus pennsylvanica` -> `green_ash`. Other `Fraxinus` is decided in the design note.
   - A string not in the crosswalk returns `None`. The tree is dropped from the host inventory. It is a non-host with weight 0.0.
   - A function `to_engine_species(raw_string) -> str | None`.
2. Per-site host inventory builder:
   1. Read the POS points. Keep `site_typ == "T"` with a crosswalk hit.
   2. Reproject to EPSG:32610. This gives absolute meters, in the same frame as `known_cases.csv` and `grid_meta` `origin_x`/`origin_y`.
   3. Clip to each site AOI box (`origin_x .. origin_x + n_cols * resolution_m`, `origin_y .. origin_y + n_rows * resolution_m`).
   4. Emit a DataFrame with columns `tree_id, x, y, species, dbh_in, stress_index, infected`. The `stress_index` default is set in the design note (see Open questions). `infected = False`.
   5. Concatenate the site's `known_cases.csv` rows (`infected = True`) as the source points.
   - Where this code runs (arcpy vs plain venv) is the main open question below.
3. Run script (`PathogenPy/run_real_site_tree_risk.py`, new):
   - A `RUNS` list mirrors `run_real_site_risk_raster.py`: `("red_ring_rot", "site", ...)`, `("phytophthora", "site_phytophthora", ...)`, `("anthracnose", "site_anthracnose", ...)`.
   - Per run:
     1. Build the inventory.
     2. Call `load_site_grid(data_dir)` for `environment`.
     3. Load `wind_rose.json` the same way `run_real_site_risk_raster.py` does.
     4. Call `compute_risk(inventory, config, environment, wind=wind)`.
   - Outputs:
     - `outputs/<pathogen>_site_tree_risk.csv`: all non-infected host trees, sorted by `risk_score` descending. It includes the component columns (`dispersal_score`, `susceptibility`, `environmental_match`, `stress_amplification`).
     - `outputs/<pathogen>_site_tree_risk_preview.png`: a per-tree scatter colored by `risk_score`. Known cases are marked. The style matches `run_red_ring_rot_grove.py`.
   - Plain `.venv`. This script does not import arcpy.

## Outputs
1. `PathogenPy/species_crosswalk.py`.
2. `PathogenPy/run_real_site_tree_risk.py`.
3. The clip and reproject code. It depends on the chosen approach: a new function in `export_site_layers.py`, or a new stdlib reader module. See Open questions.
4. Per site: `data/<site_name>/host_inventory.csv`. This is the built inventory. It is cached, so the run script does not repeat the spatial work on every run.
5. `outputs/<pathogen>_site_tree_risk.csv` and `_preview.png` for the three configured pathogens.
6. This contract, a design note, and a verification note.

## Success criteria
1. `compute_risk` runs against a real inventory for all three configured pathogens without error. This is the first real-data run of that path.
2. The ranked CSV for `anthracnose` at `site_anthracnose` lists real `Platanus` / `Acer` / `Quercus` / `Cornus` trees near the two known `PlHi` cases. The trees are ordered by risk. Genera the crosswalk maps have non-zero `susceptibility`. Anything the crosswalk does not map has 0.0.
3. Directional structure is visible. For `anthracnose` and `red_ring_rot` (airborne, wind is included), higher-risk trees sit on the downwind side of the known cases. This matches the raster footprints verified in `docs/feature_contracts/wind_dispersal_and_soil_reweight.md`.
4. `run_real_site_risk_raster.py` output is unchanged. This is a regression check. The raster path is untouched.
5. Tree counts per site AOI are reported in the verification note. If a site AOI has no POS host trees, record that. Do not work around it.

## Non-goals
1. No change to `pathogens.py`. The three target pathogens already have the config they need.
2. `emerald_ash_borer` is out of scope. It has no `spatial_weights` block and no known-case location. It cannot run through either real-site path yet. `Fraxinus` is the second best represented host genus in this dataset (8,386 trees). Same deferral as `docs/feature_contracts/anthracnose_site_risk.md`.
3. No `stress_index` modeling. The POS dataset has no health field. Stress amplification is effectively disabled for POS-sourced trees (see Open questions). A future Field Maps collection can add real per-tree stress later.
4. No validation of the crosswalk against a botanist review. It is a genus/species-to-engine-key lookup. It has the same domain-judgment caveat as the pathogen weights.
5. No new heavy dependency without a decision. `pyproj`, `geopandas`, and `rasterio` are all absent from the plain `.venv`. This is on purpose.
6. No re-run of `export_site_layers.py`. The site grids and wind roses are current.

## Open questions (resolve in the design note)
1. **Where the clip / reproject / crosswalk runs.**
   - Option A (arcpy): Add a function to `export_site_layers.py`, or a sibling script in `arcpy_export/`, that writes `data/<site>/host_inventory.csv` under ArcGIS Pro's Python. This matches the established "all GIS work confined to `arcpy_export/`" pattern. Cost: the inventory build now depends on Pro.
   - Option B (stdlib): A small self-contained reader in the plain `.venv`. Shapefile point records are fixed 20-byte structures. The `.dbf` parser is already prototyped. The CRS transform is a Lambert Conformal Conic inverse plus a UTM forward. That is about 80 lines, with the same stdlib-only approach as `fetch_wind_rose.py`. Cost: this project owns that transform code. Benefit: the whole per-tree pipeline runs in the plain `.venv`, the same way `run_real_site_risk_raster.py` runs today.
   - Recommendation: Option B. It keeps the per-tree path reproducible without Pro. Confirm before implementing.
2. **`stress_index` default.** `0.0` turns stress amplification off. Risk is then dispersal x susceptibility x environmental_match. The other choice is `0.5`, a neutral mid value. That inflates every tree equally. Recommendation: `0.0`, and document it. A mid value is a claim the data does not support.
3. **Non-`latifolia` / non-`pennsylvanica` `Fraxinus`.** Map to `oregon_ash` as the nearest local analog, or leave unmapped. Recommendation: leave unmapped. Only the two named species have a defensible engine key.
4. **`known_cases.csv` species vocab.** Source rows use codes like `PsMe` / `PlHi`. The crosswalk targets full strings. `compute_risk` never reads a source's species. It reads only the targets' species. So sources need no crosswalk. Confirm this stays true and note it.

## Definition of done
1. This contract exists (done).
2. The design note resolves the four open questions (done, `docs/notes/site_tree_host_inventory.md`; Option B).
3. `shapefile_reader.py`, `crs_transform.py`, `species_crosswalk.py`, `site_tree_inventory.py`, and `run_real_site_tree_risk.py` exist and run in the plain `.venv` (done, 2026-09-07).
4. All three pathogens produce a ranked CSV and a preview PNG (done).
5. `run_real_site_risk_raster.py` re-run and confirmed unchanged (done).
6. Verification recorded below (done, 2026-09-07).

## Verification (2026-09-07)

### Coordinate transform (`crs_transform.py`)
- UTM 10N forward and inverse round-trip to < 1e-3 m. The LCC (Oregon South State Plane) inverse and forward round-trip to 0.0000 mm across the POS bounding box and interior points.
- LCC origin check: (41.66667 N, 120.5 W) maps to easting 4,921,259.843 ift (the `.prj` false easting). Northing is 0.000.
- The composed StatePlane-ift to UTM 10N transform places all 111,323 POS points in a bounding box of lat 43.976-44.135, lon -123.206 to -123.004 (Eugene). The trees land inside the arcpy-built site AOI boxes. No datum shift is applied. NAD83(HARN) to WGS84 is treated as identity. This is standard at this accuracy class.
- Not run: an `arcpy.PointGeometry(...).projectAs(...)` cross-check. There is no arcpy in the plain `.venv`. The check is optional, given the round-trip and origin evidence above.

### Per-site host counts (in-AOI -> `site_typ == "T"` -> crosswalked host)
- `site` (red_ring_rot): 3,952 -> 3,331 -> 2,147.
  Hosts: douglas_fir 807, oak 398, maple 332, pine 323, oregon_ash 196, dogwood 43, sycamore 24, green_ash 18, western_hemlock 6.
- `site_phytophthora`: 2,269 -> 1,951 -> 1,084.
  Hosts: maple 570, oak 229, oregon_ash 120, douglas_fir 66, green_ash 32, pine 33, dogwood 19, sycamore 10, western_hemlock 5.
- `site_anthracnose`: 5,912 -> 4,911 -> 2,330.
  Hosts: maple 1,041, oak 704, douglas_fir 177, sycamore 129, oregon_ash 119, pine 81, green_ash 54, dogwood 19, western_hemlock 6.
- One null-geometry POS record (of 111,324) is dropped by the reader.

### Ranked risk output
- `compute_risk` runs against a real inventory for all three pathogens with no error. This is the first real-data run of the per-tree path.
- red_ring_rot: 2,147 hosts. 28 have `risk_score > 0`. Peak 0.214. The top trees are `douglas_fir` (susceptibility 0.9) near the known case.
- anthracnose: 2,330 hosts. 46 have `risk_score > 0`. Peak 0.086. The top 5 are all `sycamore` (`Platanus`, susceptibility 0.9) near the two known `PlHi` cases. This matches success criterion 2.
- phytophthora: 1,084 hosts. 0 have `risk_score > 0`. The nearest crosswalked host is 84.6 m from the known case. `max_dispersal_distance_m` is 25. This is a correct null result. POS (parks and open-space) coverage has no host within root-contact range of this case. The raster path still produces the suitability footprint for this site.

### Wind (per-tree check)
- With and without `wind`: red_ring_rot has 28 trees change (max |delta| 0.072). anthracnose has 46 trees change (max |delta| 0.013). phytophthora has 0 trees change (exactly 0.0). This confirms the `transmission_mode` check works on `compute_risk`. It works the same way as verified for `compute_risk_raster` in `wind_dispersal_and_soil_reweight.md`.
- Directionality, refining success criterion 3: Wind reorders the top 10 for both airborne pathogens. The top 20 are not strongly downwind-clustered. Mean |bearing - downwind| is about 100 deg for red_ring_rot and 73 deg for anthracnose. Discrete tree positions and `environmental_match` control the per-tree ranking more than the kernel's decay-rate modulation does. The smooth downwind lobe seen in the raster verification does not show up as a visible skew in a discrete ranking of a few dozen trees.

### Regression and completeness
- `run_real_site_risk_raster.py` re-run: risk ranges unchanged (red_ring_rot 0.000-0.405, phytophthora 0.000-0.079, anthracnose 0.000-0.229). `git status` shows no tracked `outputs/` file modified.
- AOI-clip completeness: with a 1,000 m AOI half-width and a 200 m maximum `max_dispersal_distance_m`, every host outside the box is more than 200 m from every source. Each such host scores 0. The ranked CSV is the complete at-risk list for each site. It is not a partial list cut from a larger set.

### Follow-ups
- `emerald_ash_borer` still cannot run through either real-site path (no `spatial_weights`, no known-case location). `Fraxinus` is well represented in the POS data (oregon_ash + green_ash: `site` 214, `site_phytophthora` 152, `site_anthracnose` 173). It is the obvious next candidate once it gets a config block and a case.
- The phytophthora null result points to one of two follow-ups. Either widen the host crosswalk (currently no `Acer`/`Quercus` within 25 m), or accept that the per-tree path adds nothing for a 25 m-dispersal pathogen against a parks-only inventory.
