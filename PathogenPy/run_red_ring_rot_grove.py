"""
Runs a site-specific prototype for a Douglas-fir grove affected by red ring rot.
"""

from pathlib import Path

import matplotlib.pyplot as plt

from pathogens import PATHOGENS
from spatial_inputs import generate_synthetic_spatial_surfaces
from spread_engine import compute_risk
from synthetic_data import generate_douglas_fir_grove_inventory


def main():
    inventory = generate_douglas_fir_grove_inventory(
        n_trees=140,
        area_size_m=1200,
        n_index_cases=4,
        seed=11,
    )
    environment = generate_synthetic_spatial_surfaces(area_size_m=1200, resolution_m=50, seed=5)
    config = PATHOGENS["red_ring_rot"]

    result = compute_risk(inventory, config, environment)
    at_risk = result[~result["infected"]].copy()
    ranked = at_risk.sort_values("risk_score", ascending=False).head(10)

    print("Douglas-fir grove scenario: red ring rot")
    print("Initial infected trees:")
    print(result[result["infected"]][["tree_id", "species", "x", "y"]].to_string(index=False))
    print("\nHighest-risk trees:")
    print(
        ranked[[
            "tree_id",
            "species",
            "stress_index",
            "risk_score",
            "dispersal_score",
            "susceptibility",
            "environmental_match",
            "stress_amplification",
        ]].to_string(index=False)
    )

    output_dir = Path(__file__).resolve().parent.parent / "outputs"
    output_dir.mkdir(exist_ok=True)
    output_path = output_dir / "red_ring_rot_grove.png"

    fig, ax = plt.subplots(figsize=(7, 7))
    infected = result[result["infected"]]
    at_risk_plot = result[~result["infected"]]

    scatter = ax.scatter(
        at_risk_plot["x"],
        at_risk_plot["y"],
        c=at_risk_plot["risk_score"],
        cmap="YlOrRd",
        s=45,
        vmin=0,
        vmax=1,
        edgecolors="none",
    )
    ax.scatter(infected["x"], infected["y"], c="black", marker="x", s=90, label="infected")
    ax.set_title("Douglas-fir grove red ring rot prototype")
    ax.set_xlabel("x (m)")
    ax.set_ylabel("y (m)")
    ax.legend(loc="upper right", fontsize=8)
    fig.colorbar(scatter, ax=ax, label="Risk score")
    fig.tight_layout()
    fig.savefig(output_path, dpi=150)

    print(f"\nSaved {output_path}")


if __name__ == "__main__":
    main()
