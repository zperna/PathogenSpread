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
    ("anthracnose", "site_anthracnose", "anthracnose_site_risk"),
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

    # Site-specific wind rose (see PathogenPy/fetch_wind_rose.py), fed into
    # compute_risk_raster's optional wind bias -- the engine itself gates
    # this to airborne/vector transmission_mode, so it's a no-op for a
    # soil-borne pathogen like phytophthora even though the file exists for
    # every site. Not stored on the pathogen config in pathogens.py because
    # prevailing wind is a property of the site's nearest station, not of
    # the pathogen -- see docs/feature_contracts/
    # wind_dispersal_and_soil_reweight.md Part B verification note.
    wind = None
    wind_rose_path = data_dir / "wind_rose.json"
    if wind_rose_path.exists():
        with open(wind_rose_path) as f:
            wind_rose = json.load(f)
        wind = {
            "prevailing_direction_deg": wind_rose["prevailing_direction_deg"],
            "directionality_strength": wind_rose["directionality_strength"],
        }

    risk = compute_risk_raster(config, environment, source_xy, wind=wind)

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

    # Zoom to the risk footprint and auto-scale the color range to its own
    # data, rather than a shared 0-1 scale across the full 2km AOI. A fixed
    # 0-1 scale makes tight, low-magnitude footprints (e.g. phytophthora's
    # 25m dispersal radius topping out around 0.13) look flat/empty even
    # though the raster has real structure -- see docs/notes/
    # real_site_risk_raster.md's resolution-bump verification.
    resolution_m = environment["resolution_m"]
    nonzero_rows, nonzero_cols = np.nonzero(risk)
    source_cols = np.clip(
        ((sources["x"].to_numpy() - environment["origin_x"]) / resolution_m).astype(int),
        0, risk.shape[1] - 1,
    )
    source_rows = np.clip(
        ((sources["y"].to_numpy() - environment["origin_y"]) / resolution_m).astype(int),
        0, risk.shape[0] - 1,
    )
    all_rows = np.concatenate([nonzero_rows, source_rows])
    all_cols = np.concatenate([nonzero_cols, source_cols])

    pad_cells = 10
    r0 = max(0, all_rows.min() - pad_cells)
    r1 = min(risk.shape[0], all_rows.max() + pad_cells + 1)
    c0 = max(0, all_cols.min() - pad_cells)
    c1 = min(risk.shape[1], all_cols.max() + pad_cells + 1)
    window = risk[r0:r1, c0:c1]

    extent = [
        environment["origin_x"] + c0 * resolution_m,
        environment["origin_x"] + c1 * resolution_m,
        environment["origin_y"] + r0 * resolution_m,
        environment["origin_y"] + r1 * resolution_m,
    ]
    fig, ax = plt.subplots(figsize=(7, 7))
    im = ax.imshow(window, cmap="YlOrRd", origin="lower", extent=extent)
    ax.scatter(sources["x"], sources["y"], c="black", marker="x", s=90, label="known case")
    ax.set_title(f"{config['display_name']} site risk raster\n(zoomed to footprint, peak {risk.max():.3f})")
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
