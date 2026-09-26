"""
Exports the existing per-tree CSVs (run_real_site_tree_risk.py,
run_real_site_tree_spread.py) and each site's known_cases.csv as point
shapefiles, so they can be added to PathogenProject.aprx directly and
rendered with graduated or categorical symbology -- no interpolation,
no raster.

See docs/feature_contracts/tree_point_export.md and
docs/notes/tree_point_export.md for why a shapefile rather than a
rasterized surface, and for the field-name crosswalk below. The
known_cases.csv export was named there as a natural follow-up, not built
until now -- lets a map show sources and ranked/spread trees together
without reopening known_cases.csv separately.

Pure format conversion: reads CSVs already written and verified
elsewhere (by the two run scripts, or by export_site_layers.py for
known_cases.csv), does not call compute_risk or simulate_spread itself.
Run with the plain project .venv -- no arcpy.
"""

from pathlib import Path

import pandas as pd

from shapefile_writer import write_point_shapefile

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_ROOT = PROJECT_ROOT / "data"
OUTPUT_DIR = PROJECT_ROOT / "outputs"
GIS_OUTPUT_DIR = OUTPUT_DIR / "gis"

PATHOGEN_KEYS = ["red_ring_rot", "phytophthora", "anthracnose"]
SITE_FOR_PATHOGEN = {
    "red_ring_rot": "site",
    "phytophthora": "site_phytophthora",
    "anthracnose": "site_anthracnose",
}

# CSV column -> (dbf field name, dbf type, length, decimals). dBASE field
# names are capped at 10 characters -- see docs/notes/tree_point_export.md
# for the full crosswalk table this mirrors.
RISK_COLUMN_MAP = {
    "tree_id": ("TREE_ID", "C", 15, 0),
    "species": ("SPECIES", "C", 16, 0),
    "dbh_in": ("DBH_IN", "N", 6, 1),
    "risk_score": ("RISK_SCORE", "N", 10, 6),
    "dispersal_score": ("DISP_SCORE", "N", 10, 6),
    "susceptibility": ("SUSCEPT", "N", 10, 6),
    "environmental_match": ("ENV_MATCH", "N", 10, 6),
    "stress_amplification": ("STRESS_AMP", "N", 10, 6),
}
SPREAD_COLUMN_MAP = {
    "tree_id": ("TREE_ID", "C", 15, 0),
    "species": ("SPECIES", "C", 16, 0),
    "dbh_in": ("DBH_IN", "N", 6, 1),
    "is_initial_case": ("INIT_CASE", "L", 1, 0),
    "infected_at_step": ("INF_STEP", "N", 3, 0),
    "risk_at_infection": ("RISK_INF", "N", 10, 6),
    "infected": ("INFECTED", "L", 1, 0),
}
# known_cases.csv (written by arcpy_export/export_site_layers.py) keeps
# its source species code (e.g. PsMe, PlHi) unconverted -- compute_risk
# never reads a source's species, so no crosswalk applies here, same as
# noted in docs/notes/site_tree_host_inventory.md open question 4.
KNOWN_CASE_COLUMN_MAP = {
    "tree_id": ("TREE_ID", "C", 15, 0),
    "species": ("SPECIES", "C", 16, 0),
    "stress_index": ("STRESS_IDX", "N", 10, 6),
    "infected": ("INFECTED", "L", 1, 0),
}


def _export_one(csv_path, column_map, shp_path):
    df = pd.read_csv(csv_path)
    field_spec = [column_map[col] for col in column_map if col in df.columns]

    records = []
    for row in df.to_dict(orient="records"):
        record = {"x": row["x"], "y": row["y"]}
        for csv_col, (dbf_name, *_rest) in column_map.items():
            if csv_col in row:
                record[dbf_name] = row[csv_col]
        records.append(record)

    write_point_shapefile(shp_path, records, field_spec)
    print(f"Wrote {shp_path} ({len(records)} points)")


def main():
    GIS_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for pathogen_key in PATHOGEN_KEYS:
        risk_csv = OUTPUT_DIR / f"{pathogen_key}_site_tree_risk.csv"
        if risk_csv.exists():
            _export_one(risk_csv, RISK_COLUMN_MAP, GIS_OUTPUT_DIR / f"{pathogen_key}_site_tree_risk.shp")
        else:
            print(f"SKIP (missing): {risk_csv}")

        spread_csv = OUTPUT_DIR / f"{pathogen_key}_site_tree_spread.csv"
        if spread_csv.exists():
            _export_one(spread_csv, SPREAD_COLUMN_MAP, GIS_OUTPUT_DIR / f"{pathogen_key}_site_tree_spread.shp")
        else:
            print(f"SKIP (missing): {spread_csv}")

        known_cases_csv = DATA_ROOT / SITE_FOR_PATHOGEN[pathogen_key] / "known_cases.csv"
        if known_cases_csv.exists():
            _export_one(known_cases_csv, KNOWN_CASE_COLUMN_MAP, GIS_OUTPUT_DIR / f"{pathogen_key}_known_cases.shp")
        else:
            print(f"SKIP (missing): {known_cases_csv}")


if __name__ == "__main__":
    main()
