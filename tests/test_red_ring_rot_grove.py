from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[1] / "PathogenPy"))

from pathogens import PATHOGENS
from spread_engine import compute_risk
from synthetic_data import (
    generate_douglas_fir_grove_inventory,
    generate_environment_grid,
)


def test_grove_inventory_and_risk_output():
    inventory = generate_douglas_fir_grove_inventory(n_trees=60, n_index_cases=3, seed=11)
    environment = generate_environment_grid(area_size_m=1200, resolution_m=50, seed=5)

    assert inventory["infected"].sum() == 3
    assert (inventory["species"] == "douglas_fir").sum() > 0.6 * len(inventory)

    result = compute_risk(inventory, PATHOGENS["red_ring_rot"], environment)

    assert "risk_score" in result.columns
    assert "dispersal_score" in result.columns
    assert "susceptibility" in result.columns
    assert result.loc[~result["infected"], "risk_score"].max() > 0
