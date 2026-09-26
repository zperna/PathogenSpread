"""
Builds a per-site host-tree inventory for the per-tree risk path
(spread_engine.compute_risk), from the City of Eugene POS tree layer.

See docs/feature_contracts/site_tree_host_inventory.md and
docs/notes/site_tree_host_inventory.md.

Pipeline per site:
1. read data/POS_Trees_Master (once, cached),
2. keep site_typ == "T" (a standing tree, not a stump or planting site),
3. transform each point StatePlane-ift -> UTM 10N meters,
4. clip to the site's AOI box from grid_meta.json,
5. crosswalk Tree_speci -> engine host key, drop non-hosts,
6. append the site's known_cases.csv rows as the infected source points.

Runs in the plain .venv -- no arcpy, no geopandas.
"""

import json
from pathlib import Path

import pandas as pd

from crs_transform import stateplane_or_south_ift_to_utm10n
from shapefile_reader import read_point_shapefile
from spatial_inputs import load_known_cases
from species_crosswalk import to_engine_species

PROJECT_ROOT = Path(__file__).resolve().parent.parent
POS_SHAPEFILE_STEM = PROJECT_ROOT / "data" / "POS_Trees_Master" / "POS_Trees_Master"

TREE_SITE_TYPE = "T"  # vs "S" stump, "P" planting site -- see design note
POS_STRESS_INDEX_DEFAULT = 0.0  # dataset has no health field; see design note

_pos_features_cache = None


def _load_pos_features():
    """POS shapefile rows, read once per process (111k records)."""
    global _pos_features_cache
    if _pos_features_cache is None:
        _pos_features_cache = read_point_shapefile(POS_SHAPEFILE_STEM)
    return _pos_features_cache


def _parse_diameter(raw):
    """POS `diameter` is text; blanks and '***' become None."""
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _aoi_box(site_data_dir):
    with open(Path(site_data_dir) / "grid_meta.json") as f:
        meta = json.load(f)
    x0 = meta["origin_x"]
    y0 = meta["origin_y"]
    x1 = x0 + meta["n_cols"] * meta["resolution_m"]
    y1 = y0 + meta["n_rows"] * meta["resolution_m"]
    return x0, y0, x1, y1


def build_host_inventory(site_data_dir, write_cache=True):
    """
    Returns a DataFrame with columns
    tree_id, x, y, species, dbh_in, stress_index, infected

    - Host rows: POS "T" trees inside the AOI whose Tree_speci maps to an
      engine host key, infected=False, stress_index=0.0.
    - Source rows: known_cases.csv rows with infected==True, appended
      unchanged (dbh_in null). compute_risk reads a source's position
      only, never its species, so the PsMe/PlHi codes there need no
      crosswalk.
    """
    site_data_dir = Path(site_data_dir)
    x0, y0, x1, y1 = _aoi_box(site_data_dir)

    host_rows = []
    for feature in _load_pos_features():
        if feature.get("site_typ") != TREE_SITE_TYPE:
            continue
        engine_species = to_engine_species(feature.get("Tree_speci", ""))
        if engine_species is None:
            continue
        x_m, y_m = stateplane_or_south_ift_to_utm10n(feature["x"], feature["y"])
        if not (x0 <= x_m <= x1 and y0 <= y_m <= y1):
            continue
        host_rows.append({
            "tree_id": f"POS{feature.get('OBJECTID', '')}",
            "x": x_m,
            "y": y_m,
            "species": engine_species,
            "dbh_in": _parse_diameter(feature.get("diameter")),
            "stress_index": POS_STRESS_INDEX_DEFAULT,
            "infected": False,
        })

    hosts = pd.DataFrame(
        host_rows,
        columns=["tree_id", "x", "y", "species", "dbh_in", "stress_index", "infected"],
    )

    known = load_known_cases(site_data_dir / "known_cases.csv")
    sources = known[known["infected"]].copy()
    sources["dbh_in"] = pd.NA
    sources = sources[["tree_id", "x", "y", "species", "dbh_in", "stress_index", "infected"]]

    inventory = pd.concat([hosts, sources], ignore_index=True)

    if write_cache:
        inventory.to_csv(site_data_dir / "host_inventory.csv", index=False)

    return inventory
