from pathlib import Path
import sys

import pandas as pd
import pytest

sys.path.append(str(Path(__file__).resolve().parents[1] / "PathogenPy"))

from pathogens import PATHOGENS
from spread_simulation import STALL_CAP, simulate_spread

# With no environment, environmental_match is a neutral 0.5. So the
# single-step hazard for a host is exp(-0.01 * distance_m) * 0.5. A
# threshold of 0.3 is reached at distances up to 51.08 m.
CONFIG = {
    "display_name": "Test pathogen",
    "transmission_mode": "soil",
    "max_dispersal_distance_m": 100,
    "decay_rate": 0.01,
    "host_susceptibility": {"host": 1.0},
    "stress_multiplier": 1.0,
    "spread_step": {"promotion_threshold": 0.3, "step_label": "generation"},
}


def line_inventory():
    """One source at x=0. Hosts at 40 m spacing, then a 80 m gap. One
    non-host stands next to the source."""
    rows = [
        ("SRC", 0.0, "host", True),
        ("A", 40.0, "host", False),
        ("B", 80.0, "host", False),
        ("C", 120.0, "host", False),
        ("FAR", 200.0, "host", False),
        ("NONHOST", 10.0, "other", False),
    ]
    return pd.DataFrame({
        "tree_id": [r[0] for r in rows],
        "x": [r[1] for r in rows],
        "y": 0.0,
        "species": [r[2] for r in rows],
        "stress_index": 0.0,
        "infected": [r[3] for r in rows],
    })


def step_of(result, tree_id):
    return result.loc[result["tree_id"] == tree_id, "infected_at_step"].iloc[0]


def test_infection_moves_one_tree_per_generation_then_stalls():
    result, log = simulate_spread(line_inventory(), CONFIG)

    assert step_of(result, "SRC") == 0
    assert step_of(result, "A") == 1
    assert step_of(result, "B") == 2
    assert step_of(result, "C") == 3
    assert pd.isna(step_of(result, "FAR"))

    assert [entry["newly_infected"] for entry in log] == [["A"], ["B"], ["C"], []]
    assert [entry["cumulative_infected"] for entry in log] == [2, 3, 4, 4]


def test_non_host_is_never_infected():
    result, _ = simulate_spread(line_inventory(), CONFIG)

    non_host = result[result["tree_id"] == "NONHOST"].iloc[0]
    assert not non_host["infected"]
    assert pd.isna(non_host["infected_at_step"])


def test_risk_at_infection_reaches_the_threshold():
    result, _ = simulate_spread(line_inventory(), CONFIG)

    promoted = result[result["infected"] & ~result["is_initial_case"]]
    assert len(promoted) == 3
    assert (promoted["risk_at_infection"].astype(float) >= 0.3).all()
    assert promoted["risk_at_infection"].astype(float).iloc[0] == pytest.approx(0.33516, abs=1e-5)


def test_n_steps_limits_the_run():
    result, log = simulate_spread(line_inventory(), CONFIG, n_steps=1)

    assert len(log) == 1
    assert int(result["infected"].sum()) == 2


def test_run_is_deterministic_and_seed_has_no_effect():
    first, first_log = simulate_spread(line_inventory(), CONFIG, seed=1)
    second, second_log = simulate_spread(line_inventory(), CONFIG, seed=2)

    assert first_log == second_log
    assert first["infected"].tolist() == second["infected"].tolist()


def test_input_inventory_is_not_changed():
    inventory = line_inventory()
    before = inventory.copy()

    simulate_spread(inventory, CONFIG)

    pd.testing.assert_frame_equal(inventory, before)


def test_no_initial_case_gives_empty_log():
    inventory = line_inventory()
    inventory["infected"] = False

    result, log = simulate_spread(inventory, CONFIG)

    assert log == []
    assert not result["infected"].any()


def test_missing_spread_step_raises_clear_error():
    config = {key: value for key, value in CONFIG.items() if key != "spread_step"}

    with pytest.raises(ValueError, match="spread_step"):
        simulate_spread(line_inventory(), config)


def test_run_without_n_steps_stops_at_stall_cap():
    # 40 hosts in a chain. Each generation infects exactly one more tree.
    n_hosts = 40
    inventory = pd.DataFrame({
        "tree_id": ["SRC"] + [f"T{i}" for i in range(1, n_hosts + 1)],
        "x": [40.0 * i for i in range(n_hosts + 1)],
        "y": 0.0,
        "species": "host",
        "stress_index": 0.0,
        "infected": [True] + [False] * n_hosts,
    })

    result, log = simulate_spread(inventory, CONFIG)

    assert len(log) == STALL_CAP
    assert int(result["infected"].sum()) == 1 + STALL_CAP


def test_every_real_site_pathogen_has_a_valid_threshold():
    for key in ("red_ring_rot", "phytophthora", "anthracnose"):
        threshold = PATHOGENS[key]["spread_step"]["promotion_threshold"]
        assert 0 < threshold <= 1
