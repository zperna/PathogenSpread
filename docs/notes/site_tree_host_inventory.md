# Design note: real per-tree host inventory from the Eugene tree dataset

Companion to `docs/feature_contracts/site_tree_host_inventory.md`.
Approach chosen: Option B. It is stdlib-only, runs in the plain `.venv`, and needs no arcpy and no new dependency.

## Resolved open questions

1. **Where the clip / reproject / crosswalk runs.** Plain `.venv`, stdlib only. The POS layer is a static local file, not a live service. It does not need arcpy. Shapefile point records have a fixed size. The `.dbf` reader is simple. The coordinate transform is a closed-form Lambert Conformal Conic inverse, followed by a Transverse Mercator (UTM) forward. The whole per-tree path runs the same way as `run_real_site_risk_raster.py`.
2. **`stress_index` default: `0.0`.** The POS dataset has no health, condition, or vigor field. `compute_risk` computes `stress_amp = 1 + (stress_multiplier - 1) * stress_index`. So `0.0` gives `stress_amp = 1.0`, which means no amplification. A neutral `0.5` would inflate every tree's risk by a fixed factor. It would also imply a stress reading that the data does not contain. The output CSV records this as a real column. A later Field Maps collection can overwrite it.
3. **Non-`latifolia` / non-`pennsylvanica` `Fraxinus`: unmapped.** Only `Fraxinus latifolia` -> `oregon_ash` and `Fraxinus pennsylvanica` -> `green_ash` get an engine key. Other ash (ornamental cultivars, `Fraxinus spp`) has no defensible susceptibility value in any current pathogen config. So these trees are dropped as non-hosts. This matters only for a future `emerald_ash_borer` run, which is out of scope.
4. **`known_cases.csv` species vocab: no crosswalk needed for sources.** `compute_risk` maps `host_susceptibility` over targets only (`targets["species"].map(...)`). Source rows (`infected == True`) contribute position and nothing else. The `PsMe` / `PlHi` codes in `known_cases.csv` are never looked up, so they can stay as they are. A one-line comment in the run script will state this. That stops someone from "fixing" it later by mistake.

## Module layout

New files, all in `PathogenPy/`:

1. `shapefile_reader.py`: a stdlib `.shp` + `.dbf` reader for points only.
   - `read_point_shapefile(path_stem) -> list[dict]`: one dict per record, `{"x": float, "y": float, **dbf_fields}`. Null shapes are skipped. The file has one. `.dbf` deletion-flag rows are skipped.
   - `.shp` parse:
     1. Skip the 100-byte header.
     2. Loop over the records. Each has an 8-byte big-endian record header (`record number`, `content length` in 16-bit words).
     3. Read `content length * 2` bytes. The first 4 bytes, little-endian, give the shape type (`1` = point, `0` = null).
     4. The next 16 bytes are two little-endian doubles, `x, y`.
   - `.dbf` parse:
     1. The 32-byte file header gives the record count, header length, and record length.
     2. Read the 32-byte field descriptors until the `0x0D` terminator.
     3. Each record starts with a 1-byte flag (`0x20` live, `0x2A` deleted). Field values are fixed-width text, stripped.
     4. Decode as `latin1`, so no byte sequence can raise an error. The only fields this feature reads (`site_typ`, `Tree_speci`, `diameter`) are ASCII in the part that matters. The `.cpg` says UTF-8. But the common-name text has stray cp1252 em dash bytes (`0x97`). So `latin1` with "leading tokens only" is the safe read.
2. `crs_transform.py`: a closed-form geodetic transform, using stdlib `math`.
   - `stateplane_or_south_ift_to_utm10n(x_ft, y_ft) -> (x_m, y_m)`.
   - It runs in two steps. First, `stateplane -> lat/lon`: LCC 2SP inverse, GRS80, standard parallels 44.0 and 42.33333, latitude of origin 41.66667, central meridian -120.5, false easting 1,500,000 m, International-foot input scaled by 0.3048. Second, `lat/lon -> UTM 10N`: Snyder Transverse Mercator forward series, `k0 = 0.9996`, central meridian -123, false easting 500,000. GRS80 and WGS84 flattening differ at the 1e-10 level. That is negligible at tree positional accuracy. So one ellipsoid constant set serves both steps.
   - Parameters come from `data/POS_Trees_Master/POS_Trees_Master.prj`. They are hard-coded as named constants, with the `.prj` string quoted in a comment. If a future dataset uses a different CRS, this module gets a new function. It does not become a general projection engine.
3. `species_crosswalk.py`: `POS_SPECIES_TO_ENGINE` dict and `to_engine_species(raw_tree_speci: str) -> str | None`.
   - Match order: the exact `Tree_speci` string first, then the leading genus token.
   - Genus map: `Acer -> maple`, `Quercus -> oak`, `Pseudotsuga -> douglas_fir`, `Cornus -> dogwood`, `Platanus -> sycamore`, `Pinus -> pine`, `Tsuga -> western_hemlock`.
   - Species map (checked before the genus fallback): `Fraxinus latifolia -> oregon_ash`, `Fraxinus pennsylvanica -> green_ash`.
   - `"Unknown"`, blank, and every unlisted genus return `None`.
4. `site_tree_inventory.py`: builds one site's host inventory.
   - `build_host_inventory(site_data_dir) -> DataFrame` with columns `tree_id, x, y, species, dbh_in, stress_index, infected`.
   - Steps:
     1. Read the POS shapefile once. A module-level cache keeps the three sites from each re-reading 111k records.
     2. Keep `site_typ == "T"`.
     3. Transform each kept point to UTM 10N.
     4. Keep points inside the AOI box from `grid_meta.json` (`origin_x .. origin_x + n_cols * resolution_m`, same for y).
     5. Crosswalk `Tree_speci`. Drop `None`.
     6. Set `stress_index = 0.0`, `infected = False`, and `tree_id = f"POS{OBJECTID}"`.
     7. Read `known_cases.csv`. Keep `infected == True` and append those rows. `dbh_in` is left null for source rows.
     8. Write `data/<site>/host_inventory.csv` as a cache. Return the DataFrame.
5. `run_real_site_tree_risk.py`: the runner. `RUNS` mirrors `run_real_site_risk_raster.py`. Per run:
   1. `build_host_inventory`.
   2. `load_site_grid`.
   3. Load `wind_rose.json` exactly as the raster runner does.
   4. `compute_risk(inventory, config, environment, wind=wind)`.
   5. Sort non-infected rows by `risk_score`, descending.
   6. Write `outputs/<pathogen>_site_tree_risk.csv` and `_preview.png`.
   - `inventory = inventory.reset_index(drop=True)` runs before the engine call. This makes the `df.loc[targets.index, ...]` writes in `compute_risk` unambiguous.

## Assumptions

1. The AOI box from `grid_meta.json` is axis-aligned in UTM 10N. It is. `export_site_layers.build_aoi_extent` builds it that way. So a plain min/max coordinate test is a correct clip. No polygon intersection is needed.
2. POS point coordinates are the tree stems. Positional accuracy of a municipal inventory is about a few meters. That is well inside the 10 m grid cell size and the dispersal kernels' distance scale. So transform error at the decimetre level does not matter.
3. `site_typ == "T"` means a standing tree. `S` (stump) and `P` (planting site) are excluded as non-hosts. The contract lists this reading as something to confirm against the dataset's metadata. If `T` turns out to include dead standing trees, the result is a small over-count of hosts. It is not a pipeline break.
4. `compute_risk` has an environmental fallback. It needs `environment["moisture"]` / `["temp"]`, and `load_site_grid` does not provide them. The fallback is never reached. All three target pathogens have `spatial_weights` that name surfaces `load_site_grid` does provide. A pathogen without `spatial_weights` (for example `emerald_ash_borer`) would raise a `KeyError` here. This is documented and out of scope.
5. Clipping the inventory to the AOI loses no at-risk tree. The AOI half-width is 1000 m. The largest `max_dispersal_distance_m` among the three configured pathogens is 200 m (anthracnose). The AOI is centered on the known cases. So any host outside the box is more than 200 m from every source. It scores exactly 0 in a single-step `compute_risk`. The ranked CSV is therefore the complete at-risk list for the site. It is not a subset of a larger list. The verification note states this, so a clipped list is not misread. This stops being true for multi-step temporal spread or for `emerald_ash_borer`'s 3 km flight range. Both are out of scope here.

## Verification plan

1. **Transform accuracy.** Project 3 POS points through ArcGIS Pro (`arcpy.PointGeometry(arcpy.Point(x, y), SpatialReference(2914)).projectAs(SpatialReference(32610))`). Compare the results to `crs_transform`. Expect sub-meter agreement. The UTM forward leg already round-trips to sub-millimetre against `crs_transform`'s own inverse in a standalone check. This step checks the LCC inverse leg against an independent implementation.
2. **Counts.** Report, per site: POS points in the AOI (all types), the count after `site_typ == "T"`, and the count after the crosswalk. Preliminary all-type, all-species counts from a dry run of the transform: `site` 3,952, `site_phytophthora` 2,269, `site_anthracnose` 5,912. So every site has a usable inventory.
3. **Ranked output sanity.** For `anthracnose` at `site_anthracnose`, the top-ranked trees should be `sycamore` / `maple` / `oak` / `dogwood`. They should sit close to the two known `PlHi` cases. `susceptibility` should match `pathogens.PATHOGENS["anthracnose"]["host_susceptibility"]`. Any genus the crosswalk does not map should show `0.0`. There should be none left in the output, because unmapped trees are dropped.
4. **Downwind skew.** Compare the top-20 trees' bearings from the nearest known case against the site's downwind direction (`prevailing_direction_deg + 180`). Expect a bias toward downwind for `anthracnose` and `red_ring_rot`. Expect none for `phytophthora` (soil, wind check off).
5. **Regression.** Re-run `run_real_site_risk_raster.py` and diff the three `outputs/*_site_risk.npy` files. They must be byte-identical. This feature does not touch the raster path.

## Update summary (2026-09-07)

- Approach fixed as Option B. The four open questions are resolved above.
- Implemented, all in `PathogenPy/`: `shapefile_reader.py`, `crs_transform.py`, `species_crosswalk.py`, `site_tree_inventory.py`, and `run_real_site_tree_risk.py`. No new dependency. Runs in the plain `.venv`.
- Ran `run_real_site_tree_risk.py` for all three sites. Full results are in the contract's "Verification (2026-09-07)" section. Headline: `compute_risk` runs on a real inventory for the first time. The anthracnose top-ranked trees are `sycamore` near the known cases, as predicted. Phytophthora returns an all-zero ranking. Its nearest crosswalked host is 84.6 m from the case, and its dispersal cap is 25 m. The `transmission_mode` wind check on the per-tree path behaves the same as on the raster path.
- Deviation from plan: there is no separate `docs/notes` verification file. The verification is recorded in the contract, matching `anthracnose_site_risk.md`.
- Not yet addressed: `emerald_ash_borer` still has no way through either real-site path. The POS `Fraxinus` records make it the obvious next candidate, once it has a `spatial_weights` block and a known-case location. Also open: whether the phytophthora per-tree path is worth keeping, given a parks-only inventory and a 25 m dispersal cap.
