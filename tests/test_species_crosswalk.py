from pathlib import Path
import sys

import pytest

sys.path.append(str(Path(__file__).resolve().parents[1] / "PathogenPy"))

from pathogens import PATHOGENS
from species_crosswalk import _GENUS_TO_ENGINE, _SPECIES_TO_ENGINE, to_engine_species


@pytest.mark.parametrize("raw, expected", [
    ("Pseudotsuga menziesii - Douglas fir", "douglas_fir"),
    ("Acer macrophyllum - bigleaf maple", "maple"),
    ("Quercus garryana - Oregon white oak", "oak"),
    ("Platanus x hispanica - London plane", "sycamore"),
    ("Cornus nuttallii - Pacific dogwood", "dogwood"),
    ("Pinus ponderosa - ponderosa pine", "pine"),
    ("Tsuga heterophylla - western hemlock", "western_hemlock"),
])
def test_genus_level_match(raw, expected):
    assert to_engine_species(raw) == expected


def test_ash_is_matched_at_species_level():
    assert to_engine_species("Fraxinus latifolia - Oregon ash") == "oregon_ash"
    assert to_engine_species("Fraxinus pennsylvanica - green ash") == "green_ash"


def test_other_ash_is_not_a_host():
    assert to_engine_species("Fraxinus spp - ash") is None
    assert to_engine_species("Fraxinus americana - white ash") is None


def test_exact_scientific_name_without_common_name():
    assert to_engine_species("Fraxinus latifolia") == "oregon_ash"
    assert to_engine_species("Acer") == "maple"


@pytest.mark.parametrize("raw", ["", None, "Unknown", "Unknown - unknown", "Thuja plicata - western redcedar"])
def test_non_hosts_return_none(raw):
    assert to_engine_species(raw) is None


def test_cp1252_dash_in_common_name_does_not_break_the_match():
    assert to_engine_species("Acer rubrum - red maple \x97 cultivar") == "maple"


def test_every_crosswalk_key_is_a_host_of_some_pathogen():
    engine_hosts = set()
    for config in PATHOGENS.values():
        engine_hosts.update(config["host_susceptibility"])

    crosswalk_keys = set(_GENUS_TO_ENGINE.values()) | set(_SPECIES_TO_ENGINE.values())

    assert crosswalk_keys <= engine_hosts
