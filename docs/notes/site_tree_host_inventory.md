# Design note: real per-tree host inventory from the Eugene tree dataset

Companion to `docs/feature_contracts/site_tree_host_inventory.md`.
Approach chosen: Option B -- stdlib-only, runs in the plain `.venv`, no
arcpy and no new dependency.

## Resolved open questions

1. **Where the clip / reproject / crosswalk runs.** Plain `.venv`,
   stdlib only. The POS layer is a static local file, not a live
   service, so it does not need arcpy. Shapefile point records are
   fixed-size binary, the `.dbf` reader is simple, and the coordinate
   transform is a closed-form Lambert Conformal Conic inverse followed
   by a Transverse Mercator (UTM) forward. This keeps the whole
   per-tree path runnable the same way as `run_real_site_risk_raster.py`.
2. **`stress_index` default: `0.0`.** The POS dataset has no health,
   condition, or vigor field. `compute_risk` computes
   `stress_amp = 1 + (stress_multiplier - 1) * stress_index`, so
   `0.0` gives `stress_amp = 1.0` -- no amplification. A neutral `0.5`
   would inflate every tree's risk by a fixed factor and imply a stress
   reading the data does not contain. Recorded in the output CSV as a
   real column so a later Field Maps collection can overwrite it.
3. **Non-`latifolia` / non-`pennsylvanica` `Fraxinus`: unmapped.** Only
   `Fraxinus latifolia` -> `oregon_ash` and `Fraxinus pennsylvanica` ->
   `green_ash` get an engine key. Other ash (ornamental cultivars,
   `Fraxinus spp`) have no defensible susceptibility value in any
   current pathogen config, so they drop out as non-hosts. This only
   matters for a future `emerald_ash_borer` run, which is out of scope.
4. **`known_cases.csv` species vocab: no crosswalk needed for sources.**
   `compute_risk` maps `host_susceptibility` over targets only
   (`targets["species"].map(...)`). Source rows (`infected == True`)
   contribute position and nothing else. The `PsMe` / `PlHi` codes in
   `known_cases.csv` are never looked up, so they can stay as-is. A
   one-line comment in the run script will state this so it is not
   "fixed" later by mistake.

## Module layout

New files, all in `PathogenPy/`:

1. `shapefile_reader.py` -- stdlib `.shp` + `.dbf` reader, points only.
   - `read_point_shapefile(path_stem) -> list[dict]`: one dict per
     record, `{"x": float, "y": float, **dbf_fields}`. Null shapes
     (the file has one) are skipped. `.dbf` deletion-flag rows are
     skipped.
   - `.shp` parse: skip the 100-byte header, then loop 8-byte big-endian
     record headers (`record number`, `content length` in 16-bit words),
     read `content length * 2` bytes, first 4 bytes little-endian is the
     shape type (`1` = point, `0` = null), next 16 bytes are two
     little-endian doubles `x, y`.
   - `.dbf` parse: 32-byte file header gives record count, header
     length, record length. Then 32-byte field descriptors until the
     `0x0D` terminator. Each record starts with a 1-byte flag
     (`0x20` live, `0x2A` deleted). Field values are fixed-width text,
     stripped. Decoded `latin1` so no byte sequence can raise -- the
     only fields this feature reads (`site_typ`, `Tree_speci`,
     `diameter`) are ASCII in the part that matters; the `.cpg` claims
     UTF-8 but the common-name text contains stray cp1252 em dashes
     (`0x97`), so `latin1` + "leading tokens only" is the safe read.
2. `crs_transform.py` -- closed-form geodetic transform, stdlib `math`.
   - `stateplane_or_south_ift_to_utm10n(x_ft, y_ft) -> (x_m, y_m)`.
   - Internally: `stateplane -> lat/lon` (LCC 2SP inverse, GRS80,
     standard parallels 44.0 and 42.33333, latitude of origin
     41.66667, central meridian -120.5, false easting 1,500,000 m,
     International-foot input scaled by 0.3048) then `lat/lon -> UTM
     10N` (Snyder Transverse Mercator forward series, `k0 = 0.9996`,
     central meridian -123, false easting 500,000). GRS80 vs WGS84
     flattening differ at the 1e-10 level -- negligible at tree
     positional accuracy, so one ellipsoid constant set is used for
     both legs.
   - Parameters read from `data/POS_Trees_Master/POS_Trees_Master.prj`,
     hard-coded as named constants with the `.prj` string quoted in a
     comment. If a future dataset arrives in a different CRS this
     module gets a new function, it does not try to be a general
     projection engine.
3. `species_crosswalk.py` -- `POS_SPECIES_TO_ENGINE` dict +
   `to_engine_species(raw_tree_speci: str) -> str | None`.
   - Match order: exact `Tree_speci` string, then leading genus token.
   - Genus map: `Acer -> maple`, `Quercus -> oak`,
     `Pseudotsuga -> douglas_fir`, `Cornus -> dogwood`,
     `Platanus -> sycamore`, `Pinus -> pine`, `Tsuga -> western_hemlock`.
   - Species map (checked before the genus fallback):
     `Fraxinus latifolia -> oregon_ash`,
     `Fraxinus pennsylvanica -> green_ash`.
   - `"Unknown"`, blank, and every unlisted genus return `None`.
4. `site_tree_inventory.py` -- builds one site's host inventory.
   - `build_host_inventory(site_data_dir) -> DataFrame` with columns
     `tree_id, x, y, species, dbh_in, stress_index, infected`.
   - Steps: read POS shapefile once (module-level cache so three sites
     do not re-read 111k records three times), keep `site_typ == "T"`,
     transform every kept point to UTM 10N, keep points inside the AOI
     box from `grid_meta.json`
     (`origin_x .. origin_x + n_cols * resolution_m`, same for y),
     crosswalk `Tree_speci`, drop `None`, set `stress_index = 0.0`,
     `infected = False`, `tree_id = f"POS{OBJECTID}"`.
   - Then read `known_cases.csv`, keep `infected == True`, append.
     `dbh_in` for source rows is left null.
   - Writes `data/<site>/host_inventory.csv` as a cache and returns the
     DataFrame.
5. `run_real_site_tree_risk.py` -- the runner. `RUNS` list mirrors
   `run_real_site_risk_raster.py`. Per run: `build_host_inventory`,
   `load_site_grid`, load `wind_rose.json` exactly as the raster runner
   does, `compute_risk(inventory, config, environment, wind=wind)`,
   sort non-infected rows by `risk_score` desc, write
   `outputs/<pathogen>_site_tree_risk.csv` and `_preview.png`.
   `inventory = inventory.reset_index(drop=True)` before the engine call
   so `compute_risk`'s `df.loc[targets.index, ...]` writes are
   unambiguous.

## Assumptions

1. The AOI box from `grid_meta.json` is axis-aligned in UTM 10N (it is
   -- `export_site_layers.build_aoi_extent` builds it that way), so a
   plain min/max coordinate test is a correct clip. No polygon
   intersection needed.
2. POS point coordinates are the tree stems. Positional accuracy of a
   municipal inventory is roughly the curb-to-tree scale (a few
   meters); this is well inside the 10 m grid cell size and the
   dispersal kernels' distance scale, so transform error at the
   decimetre level is immaterial.
3. `site_typ == "T"` means a standing tree. `S` (stump) and `P`
   (planting site) are excluded as non-hosts. This reading is stated in
   the contract as a thing to confirm against the dataset's metadata;
   if `T` turns out to include dead standing trees, that is a small
   over-count of hosts, not a pipeline break.
4. `compute_risk`'s environmental fallback (which needs
   `environment["moisture"]` / `["temp"]`, absent from
   `load_site_grid`) is never reached, because all three target
   pathogens have `spatial_weights` naming surfaces that `load_site_grid`
   does provide. A pathogen without `spatial_weights` (e.g.
   `emerald_ash_borer`) would `KeyError` here -- documented, out of
   scope.
5. Clipping the inventory to the AOI box loses no at-risk tree. The AOI
   half-width is 1000 m; the largest `max_dispersal_distance_m` among
   the three configured pathogens is 200 m (anthracnose), and the AOI is
   centered on the known cases, so any host outside the box is more than
   200 m from every source and scores exactly 0 in a single-step
   `compute_risk`. The ranked CSV is therefore the complete at-risk list
   for the site, not a window onto a larger one -- the verification note
   states this so a clipped list is not misread. This stops being true
   for multi-step temporal spread or for `emerald_ash_borer`'s 3 km
   flight range, both out of scope here.

## Verification plan

1. **Transform accuracy.** Project 3 POS points through ArcGIS Pro
   (`arcpy.PointGeometry(arcpy.Point(x, y), SpatialReference(2914))
   .projectAs(SpatialReference(32610))`) and compare to
   `crs_transform`. Expect sub-meter agreement. (The UTM-forward leg
   already round-trips to sub-millimetre against `crs_transform`'s own
   inverse in a standalone check; this step pins the LCC-inverse leg to
   an independent implementation.)
2. **Counts.** Report, per site: POS points in the AOI (all types),
   after `site_typ == "T"`, after crosswalk. Preliminary all-type,
   all-species counts from a dry run of the transform: `site` 3,952,
   `site_phytophthora` 2,269, `site_anthracnose` 5,912 -- so every site
   has a usable inventory.
3. **Ranked output sanity.** For `anthracnose` at `site_anthracnose`:
   top-ranked trees should be `sycamore` / `maple` / `oak` / `dogwood`
   close to the two known `PlHi` cases, with `susceptibility` matching
   `pathogens.PATHOGENS["anthracnose"]["host_susceptibility"]` and
   `0.0` for any genus the crosswalk does not map (there should be none
   left in the output, since unmapped trees are dropped).
4. **Downwind skew.** Compare the top-20 trees' bearings from the
   nearest known case against the site's downwind direction
   (`prevailing_direction_deg + 180`). Expect a lean toward downwind for
   `anthracnose` and `red_ring_rot`, none for `phytophthora` (soil,
   wind gated off).
5. **Regression.** Re-run `run_real_site_risk_raster.py`, diff the three
   `outputs/*_site_risk.npy` -- must be byte-identical, this feature
   does not touch the raster path.

## Update summary (2026-09-07)

- Approach fixed as Option B; four open questions resolved above.
- Implemented, all in `PathogenPy/`: `shapefile_reader.py`,
  `crs_transform.py`, `species_crosswalk.py`, `site_tree_inventory.py`,
  `run_real_site_tree_risk.py`. No new dependency; runs in the plain
  `.venv`.
- Ran `run_real_site_tree_risk.py` for all three sites. Full results in
  the contract's "Verification (2026-09-07)" section. Headline:
  `compute_risk` runs on a real inventory for the first time;
  anthracnose top-ranked trees are `sycamore` near the known cases as
  predicted; phytophthora returns an all-zero ranking because its
  nearest crosswalked host is 84.6 m from the case and its dispersal cap
  is 25 m; the `transmission_mode` wind gate behaves on the per-tree
  path exactly as on the raster path.
- Deviation from plan: no separate `docs/notes` verification file; the
  verification is recorded in the contract, matching
  `anthracnose_site_risk.md`.
- Not yet addressed: `emerald_ash_borer` still has no way through
  either real-site path; the POS `Fraxinus` records make it the obvious
  next candidate once it gets a `spatial_weights` block and a known-case
  location. Also open: whether the phytophthora per-tree path is worth
  keeping given a parks-only inventory and a 25 m dispersal cap.
