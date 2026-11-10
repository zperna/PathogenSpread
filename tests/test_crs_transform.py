from pathlib import Path
import sys

import pytest

sys.path.append(str(Path(__file__).resolve().parents[1] / "PathogenPy"))

from crs_transform import (
    latlon_to_utm10n,
    stateplane_or_south_ift_to_latlon,
    stateplane_or_south_ift_to_utm10n,
)

# Reference values come from arcpy 3.6 projectAs (2026-11-09). The source
# CRS is the POS_Trees_Master.prj. The target is EPSG:32610. No datum
# transformation was applied, which matches the module's stated design.
# Columns: x_ft, y_ft, utm_x_m, utm_y_m.
ARCPY_REFERENCE = [
    (4240000.0, 880000.0, 492664.0198892418, 4877681.771205371),
    (4260000.0, 860000.0, 498936.6427589321, 4871772.774971576),
    (4225000.0, 895000.0, 487959.67000733776, 4882113.533694401),
]


@pytest.mark.parametrize("x_ft, y_ft, utm_x, utm_y", ARCPY_REFERENCE)
def test_stateplane_to_utm_matches_arcpy(x_ft, y_ft, utm_x, utm_y):
    x_m, y_m = stateplane_or_south_ift_to_utm10n(x_ft, y_ft)

    assert x_m == pytest.approx(utm_x, abs=0.001)
    assert y_m == pytest.approx(utm_y, abs=0.001)


def test_stateplane_false_origin_maps_to_projection_origin():
    lat_deg, lon_deg = stateplane_or_south_ift_to_latlon(4921259.843, 0.0)

    assert lat_deg == pytest.approx(41.6666666666667, abs=1e-8)
    assert lon_deg == pytest.approx(-120.5, abs=1e-8)


def test_utm_central_meridian_gives_false_easting():
    x_m, y_m = latlon_to_utm10n(44.0, -123.0)

    assert x_m == pytest.approx(500000.0, abs=1e-6)
    assert 4_870_000 < y_m < 4_875_000


def test_utm_equator_gives_zero_northing():
    _, y_m = latlon_to_utm10n(0.0, -123.0)

    assert y_m == pytest.approx(0.0, abs=1e-6)
