"""
Prototype runner: generates synthetic data, runs the spread engine for
multiple pathogens, and plots risk maps side by side.

Run with: python3 run_prototype.py
"""

from pathlib import Path

import matplotlib.pyplot as plt

from pathogens import PATHOGENS
from synthetic_data import generate_inventory, generate_environment_grid
from spread_engine import compute_risk

AREA_SIZE_M = 2000

inventory = generate_inventory(n_trees=400, area_size_m=AREA_SIZE_M, n_index_cases=3)
environment = generate_environment_grid(area_size_m=AREA_SIZE_M)

pathogens_to_run = ["emerald_ash_borer", "phytophthora", "anthracnose", "red_ring_rot"]

fig, axes = plt.subplots(2, 2, figsize=(14, 12))
axes = axes.flatten()

for ax, key in zip(axes, pathogens_to_run):
    config = PATHOGENS[key]
    result = compute_risk(inventory, config, environment)

    infected = result[result["infected"]]
    at_risk = result[~result["infected"]]

    sc = ax.scatter(
        at_risk["x"], at_risk["y"],
        c=at_risk["risk_score"], cmap="YlOrRd",
        s=25, vmin=0, vmax=1, edgecolors="none",
    )
    ax.scatter(
        infected["x"], infected["y"],
        c="black", marker="x", s=80, label="Index case (infected)",
    )
    ax.set_title(f"{config['display_name']}  ({config['transmission_mode']})")
    ax.set_xlabel("x (m)")
    ax.set_ylabel("y (m)")
    ax.legend(loc="upper right", fontsize=8)
    plt.colorbar(sc, ax=ax, label="Risk score")

    top5 = at_risk.sort_values("risk_score", ascending=False).head(5)
    print(f"\n{config['display_name']} -- top 5 highest-risk trees:")
    print(top5[["tree_id", "species", "stress_index", "risk_score"]].to_string(index=False))

plt.tight_layout()
output_dir = Path(__file__).resolve().parent.parent / "outputs"
output_dir.mkdir(exist_ok=True)
output_path = output_dir / "risk_maps_prototype.png"
plt.savefig(output_path, dpi=150)
print(f"\nSaved {output_path}")
