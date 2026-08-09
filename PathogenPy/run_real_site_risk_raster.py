"""
Computes risk rasters over the real Oregon site grids exported by
PathogenPy/arcpy_export/export_site_layers.py (see
docs/feature_contracts/real_site_risk_raster.md).

Run with the plain project .venv -- no arcpy required. Requires each
data/<site_name>/ to already exist (run export_site_layers.py under ArcGIS
Pro's Python first).
"""

import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from pathogens import PATHOGENS
from spatial_inputs import load_known_cases, load_site_grid
from spread_engine import compute_risk_raster

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_ROOT = PROJECT_ROOT / "data"
OUTPUT_DIR = PROJECT_ROOT / "outputs"

# pathogen key in pathogens.PATHOGENS -> (data/<site_name>/, output basename)
RUNS = [
    ("red_ring_rot", "site", "red_ring_rot_site_risk"),
    ("phytophthora", "site_phytophthora", "phytophthora_site_risk"),
]


def run_one(pathogen_key, site_name, output_basename):
    data_dir = DATA_ROOT / site_name
    environment = load_site_grid(data_dir)
    known_cases = load_known_cases(data_dir / "known_cases.csv")

    sources = known_cases[known_cases["infected"]]
    if sources.empty:
        raise RuntimeError(f"{data_dir}/known_cases.csv has no infected records to anchor the raster on")
    source_xy = sources[["x", "y"]].to_numpy()

    config = PATHOGENS[pathogen_key]
    risk = compute_risk_raster(config, environment, source_xy)

    OUTPUT_DIR.mkdir(exist_ok=True)
    np.save(OUTPUT_DIR / f"{output_basename}.npy", risk)

    grid_meta = {
        "origin_x": environment["origin_x"],
        "origin_y": environment["origin_y"],
        "resolution_m": environment["resolution_m"],
        "n_rows": risk.shape[0],
        "n_cols": risk.shape[1],
    }
    with open(OUTPUT_DIR / f"{output_basename}_grid_meta.json", "w") as f:
        json.dump(grid_meta, f, indent=2)

    print(f"[{pathogen_key}] Risk raster: {risk.shape[0]}x{risk.shape[1]} cells at {environment['resolution_m']}m")
    print(f"[{pathogen_key}] Risk range: {risk.min():.3f} - {risk.max():.3f}, mean {risk.mean():.3f}")
    print(f"[{pathogen_key}] Known/source cases: {len(sources)}")

    extent = [
        environment["origin_x"],
        environment["origin_x"] + risk.shape[1] * environment["resolution_m"],
        environment["origin_y"],
        environment["origin_y"] + risk.shape[0] * environment["resolution_m"],
    ]
    fig, ax = plt.subplots(figsize=(7, 7))
    im = ax.imshow(risk, cmap="YlOrRd", vmin=0, vmax=1, origin="lower", extent=extent)
    ax.scatter(sources["x"], sources["y"], c="black", marker="x", s=90, label="known case")
    ax.set_title(f"{config['display_name']} site risk raster")
    ax.set_xlabel("x (m, UTM 10N)")
    ax.set_ylabel("y (m, UTM 10N)")
    ax.legend(loc="upper right", fontsize=8)
    fig.colorbar(im, ax=ax, label="Risk score")
    fig.tight_layout()

    preview_path = OUTPUT_DIR / f"{output_basename}_preview.png"
    fig.savefig(preview_path, dpi=150)
    plt.close(fig)
    print(f"[{pathogen_key}] Saved {preview_path}")


def main():
    for pathogen_key, site_name, output_basename in RUNS:
        run_one(pathogen_key, site_name, output_basename)


if __name__ == "__main__":
    main()
