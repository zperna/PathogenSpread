"""
Per-tree risk over the real Oregon sites, using the POS host inventory
(site_tree_inventory.build_host_inventory) as input to
spread_engine.compute_risk.

This is the per-tree companion to run_real_site_risk_raster.py: the raster
script answers "how favorable is this location for spread," this one
answers "which specific host trees near the known cases are most at risk,"
ranked. See docs/feature_contracts/site_tree_host_inventory.md.

Run with the plain project .venv -- no arcpy required. Requires
data/POS_Trees_Master/ and each data/<site_name>/ to exist.
"""

import json
from pathlib import Path

import matplotlib.pyplot as plt

from pathogens import PATHOGENS
from site_tree_inventory import build_host_inventory
from spatial_inputs import load_site_grid
from spread_engine import compute_risk

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_ROOT = PROJECT_ROOT / "data"
OUTPUT_DIR = PROJECT_ROOT / "outputs"

# pathogen key -> (data/<site_name>/, output basename), mirrors
# run_real_site_risk_raster.py's RUNS
RUNS = [
    ("red_ring_rot", "site", "red_ring_rot_site_tree_risk"),
    ("phytophthora", "site_phytophthora", "phytophthora_site_tree_risk"),
    ("anthracnose", "site_anthracnose", "anthracnose_site_tree_risk"),
]

REPORT_COLUMNS = [
    "tree_id", "species", "dbh_in", "x", "y", "risk_score",
    "dispersal_score", "susceptibility", "environmental_match",
    "stress_amplification",
]


def load_wind(site_data_dir):
    """Same wind-rose load as run_real_site_risk_raster.py -- the engine
    gates this to airborne/vector transmission_mode, so it is a no-op for
    a soil-borne pathogen even though the file exists for every site."""
    wind_rose_path = site_data_dir / "wind_rose.json"
    if not wind_rose_path.exists():
        return None
    with open(wind_rose_path) as f:
        wind_rose = json.load(f)
    return {
        "prevailing_direction_deg": wind_rose["prevailing_direction_deg"],
        "directionality_strength": wind_rose["directionality_strength"],
    }


def run_one(pathogen_key, site_name, output_basename):
    site_data_dir = DATA_ROOT / site_name
    config = PATHOGENS[pathogen_key]

    inventory = build_host_inventory(site_data_dir).reset_index(drop=True)
    environment = load_site_grid(site_data_dir)
    wind = load_wind(site_data_dir)

    result = compute_risk(inventory, config, environment, wind=wind)

    sources = result[result["infected"]]
    at_risk = result[~result["infected"]].sort_values("risk_score", ascending=False)

    OUTPUT_DIR.mkdir(exist_ok=True)
    at_risk[REPORT_COLUMNS].to_csv(OUTPUT_DIR / f"{output_basename}.csv", index=False)

    host_count = len(at_risk)
    nonzero = int((at_risk["risk_score"] > 0).sum())
    print(f"[{pathogen_key}] {host_count} host trees in AOI, {len(sources)} known cases")
    if host_count:
        print(f"[{pathogen_key}] risk_score: {at_risk['risk_score'].min():.3f} - "
              f"{at_risk['risk_score'].max():.3f}, {nonzero} trees > 0")
        print(f"[{pathogen_key}] top 5:")
        print(at_risk[["tree_id", "species", "risk_score", "dispersal_score",
                       "susceptibility", "environmental_match"]].head(5).to_string(index=False))

    fig, ax = plt.subplots(figsize=(7, 7))
    scatter = ax.scatter(
        at_risk["x"], at_risk["y"], c=at_risk["risk_score"], cmap="YlOrRd",
        s=35, vmin=0, vmax=max(at_risk["risk_score"].max(), 1e-6), edgecolors="none",
    )
    ax.scatter(sources["x"], sources["y"], c="black", marker="x", s=90, label="known case")
    ax.set_title(f"{config['display_name']} per-tree risk\n({host_count} host trees, peak "
                 f"{at_risk['risk_score'].max():.3f})" if host_count else config["display_name"])
    ax.set_xlabel("x (m, UTM 10N)")
    ax.set_ylabel("y (m, UTM 10N)")
    ax.legend(loc="upper right", fontsize=8)
    fig.colorbar(scatter, ax=ax, label="Risk score")
    fig.tight_layout()

    preview_path = OUTPUT_DIR / f"{output_basename}_preview.png"
    fig.savefig(preview_path, dpi=150)
    plt.close(fig)
    print(f"[{pathogen_key}] Saved {OUTPUT_DIR / f'{output_basename}.csv'} and {preview_path}\n")


def main():
    for pathogen_key, site_name, output_basename in RUNS:
        run_one(pathogen_key, site_name, output_basename)


if __name__ == "__main__":
    main()
