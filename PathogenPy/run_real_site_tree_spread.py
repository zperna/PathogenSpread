"""
Multi-generation what-if spread over the real Oregon sites, using the POS
host inventory as the network the infection walks along.

Companion to run_real_site_tree_risk.py (single-step ranking): this one
iterates the same per-tree hazard math with a growing infected set and
reports a trajectory -- an epidemic curve plus a per-generation map.

This is an illustrative scenario, not a forecast. promotion_threshold
(per pathogen, in pathogens.py) and the generation count are knobs, not
calibrated values. See docs/feature_contracts/temporal_spread_per_tree.md.

Run with the plain project .venv -- no arcpy.
"""

import json
import math
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from pathogens import PATHOGENS
from site_tree_inventory import build_host_inventory
from spatial_inputs import load_site_grid
from spread_simulation import simulate_spread

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_ROOT = PROJECT_ROOT / "data"
OUTPUT_DIR = PROJECT_ROOT / "outputs"

RUNS = [
    ("red_ring_rot", "site", "red_ring_rot_site_tree_spread"),
    ("phytophthora", "site_phytophthora", "phytophthora_site_tree_spread"),
    ("anthracnose", "site_anthracnose", "anthracnose_site_tree_spread"),
]

MAX_FRAME_PANELS = 12
CAVEAT = "Illustrative what-if, not a forecast"


def load_wind(site_data_dir):
    wind_rose_path = site_data_dir / "wind_rose.json"
    if not wind_rose_path.exists():
        return None
    with open(wind_rose_path) as f:
        wind_rose = json.load(f)
    return {
        "prevailing_direction_deg": wind_rose["prevailing_direction_deg"],
        "directionality_strength": wind_rose["directionality_strength"],
    }


def frame_steps(last_step):
    """Generations to draw as panels: every one if <= MAX_FRAME_PANELS,
    else an evenly spaced subset that always includes the last."""
    steps = list(range(0, last_step + 1))
    if len(steps) <= MAX_FRAME_PANELS:
        return steps
    picks = np.linspace(0, last_step, MAX_FRAME_PANELS).round().astype(int)
    return sorted(set(picks.tolist()) | {last_step})


def save_curve(log, config, threshold, initial_count, output_basename):
    steps = [0] + [entry["step"] for entry in log]
    cumulative = [initial_count] + [entry["cumulative_infected"] for entry in log]

    fig, ax = plt.subplots(figsize=(7, 4.5))
    ax.plot(steps, cumulative, marker="o")
    ax.set_xlabel(f"{config['spread_step']['step_label']}")
    ax.set_ylabel("cumulative infected trees")
    ax.set_title(f"{config['display_name']} -- spread trajectory\n"
                 f"promotion_threshold={threshold}   ({CAVEAT})")
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    path = OUTPUT_DIR / f"{output_basename}_curve.png"
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path


def save_frames(result, config, threshold, output_basename):
    last_step = int(result["infected_at_step"].dropna().max()) if result["infected_at_step"].notna().any() else 0
    steps = frame_steps(last_step)
    n = len(steps)
    ncols = min(4, n)
    nrows = math.ceil(n / ncols)

    initial = result[result["is_initial_case"]]
    step_num = result["infected_at_step"]

    fig, axes = plt.subplots(nrows, ncols, figsize=(4 * ncols, 4 * nrows), squeeze=False)
    for ax in axes.flat:
        ax.set_visible(False)

    for panel, step in enumerate(steps):
        ax = axes.flat[panel]
        ax.set_visible(True)
        infected_by_now = result[step_num.notna() & (step_num <= step) & ~result["is_initial_case"]]
        still_susceptible = result[step_num.isna() | (step_num > step)]
        still_susceptible = still_susceptible[~still_susceptible["is_initial_case"]]

        ax.scatter(still_susceptible["x"], still_susceptible["y"], s=8, c="0.8", edgecolors="none")
        if len(infected_by_now):
            ax.scatter(infected_by_now["x"], infected_by_now["y"], s=14,
                       c=infected_by_now["infected_at_step"].astype(float),
                       cmap="YlOrRd", vmin=1, vmax=max(last_step, 1), edgecolors="none")
        ax.scatter(initial["x"], initial["y"], c="black", marker="x", s=60)
        ax.set_title(f"{config['spread_step']['step_label']} {step}  "
                     f"(+{len(infected_by_now)})", fontsize=9)
        ax.set_xticks([])
        ax.set_yticks([])
        ax.set_aspect("equal")

    fig.suptitle(f"{config['display_name']} -- spread by {config['spread_step']['step_label']}   "
                 f"threshold={threshold}   ({CAVEAT})", fontsize=11)
    fig.tight_layout(rect=[0, 0, 1, 0.96])
    path = OUTPUT_DIR / f"{output_basename}_frames.png"
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path


def run_one(pathogen_key, site_name, output_basename):
    site_data_dir = DATA_ROOT / site_name
    config = PATHOGENS[pathogen_key]
    threshold = config["spread_step"]["promotion_threshold"]

    inventory = build_host_inventory(site_data_dir)
    environment = load_site_grid(site_data_dir)
    wind = load_wind(site_data_dir)

    result, log = simulate_spread(inventory, config, environment, wind=wind, n_steps=None)

    n_initial = int(result["is_initial_case"].sum())
    n_final = int(result["infected"].sum())
    generations = len(log)
    stalled = bool(log and not log[-1]["newly_infected"])

    OUTPUT_DIR.mkdir(exist_ok=True)
    columns = ["tree_id", "species", "dbh_in", "x", "y", "is_initial_case",
               "infected_at_step", "risk_at_infection", "infected"]
    result.sort_values("infected_at_step", na_position="last")[columns].to_csv(
        OUTPUT_DIR / f"{output_basename}.csv", index=False
    )

    print(f"[{pathogen_key}] {CAVEAT}. promotion_threshold={threshold}")
    print(f"[{pathogen_key}] {n_initial} initial case(s), {len(result) - n_initial} host trees in AOI")
    print(f"[{pathogen_key}] ran {generations} generation(s)"
          f"{' (stalled -- no new infections)' if stalled else ''}; "
          f"{n_final - n_initial} trees infected over the run")
    for entry in log:
        print(f"    gen {entry['step']:>2}: +{len(entry['newly_infected']):<4} "
              f"cumulative {entry['cumulative_infected']}")

    curve_path = save_curve(log, config, threshold, n_initial, output_basename)
    frames_path = save_frames(result, config, threshold, output_basename)
    print(f"[{pathogen_key}] Saved {OUTPUT_DIR / f'{output_basename}.csv'}, "
          f"{curve_path.name}, {frames_path.name}\n")


def main():
    for pathogen_key, site_name, output_basename in RUNS:
        run_one(pathogen_key, site_name, output_basename)


if __name__ == "__main__":
    main()
