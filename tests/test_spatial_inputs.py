from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[1] / "PathogenPy"))

from pathogens import PATHOGENS
from spread_engine import compute_risk
from spatial_inputs import generate_synthetic_spatial_surfaces
from synthetic_data import generate_douglas_fir_grove_inventory


def test_spatial_surface_generation():
    env = generate_synthetic_spatial_surfaces(area_size_m=1200, resolution_m=50, seed=13)

    assert "land_cover" in env
    assert env["land_cover"].min() >= 0.0
    assert env["land_cover"].max() <= 1.0
    assert "soil" in env
    assert "terrain" in env
    assert "moisture" in env
    assert "temp" in env


def test_compute_risk_with_spatial_inputs():
    inventory = generate_douglas_fir_grove_inventory(n_trees=60, n_index_cases=3, seed=11)
    environment = generate_synthetic_spatial_surfaces(area_size_m=1200, resolution_m=50, seed=13)

    result = compute_risk(inventory, PATHOGENS["red_ring_rot"], environment)

    assert "risk_score" in result.columns
    assert "environmental_match" in result.columns
    assert result.loc[~result["infected"], "risk_score"].max() > 0
