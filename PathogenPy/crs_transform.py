"""
Closed-form coordinate transform for the POS tree layer, stdlib math only
(no pyproj / arcpy -- see docs/notes/site_tree_host_inventory.md, Option B).

Single job: NAD83(HARN) StatePlane Oregon South (FIPS 3602),
International Feet  ->  WGS84 UTM Zone 10N, meters (EPSG:32610), the frame
the site grids and known_cases.csv already use.

Two legs:
1. StatePlane -> geographic: Lambert Conformal Conic (2SP) inverse.
2. geographic -> UTM 10N: Transverse Mercator forward (Snyder series).

GRS80 (source datum) and WGS84 (target) flattening differ at ~1e-10;
negligible versus a municipal inventory's few-meter point accuracy, so
one ellipsoid constant set is used for both legs.

Source CRS parameters are taken verbatim from
data/POS_Trees_Master/POS_Trees_Master.prj:

  PROJCS["NAD_1983_HARN_StatePlane_Oregon_South_FIPS_3602_Feet_Intl",
    ... PROJECTION["Lambert_Conformal_Conic"],
    PARAMETER["False_Easting",4921259.843],
    PARAMETER["Central_Meridian",-120.5],
    PARAMETER["Standard_Parallel_1",44.0],
    PARAMETER["Standard_Parallel_2",42.3333333333333],
    PARAMETER["Latitude_Of_Origin",41.6666666666667],
    UNIT["foot",0.3048]]

This is not a general projection engine. A dataset in a different CRS gets
its own function here.
"""

import math

# --- GRS80 / WGS84 ellipsoid ---
_A = 6378137.0
_INV_F = 298.257222101
_F = 1.0 / _INV_F
_E2 = _F * (2.0 - _F)
_E = math.sqrt(_E2)

_INTL_FOOT_M = 0.3048

# --- LCC 2SP: Oregon South State Plane ---
_LCC_LAT1 = math.radians(44.0)
_LCC_LAT2 = math.radians(42.3333333333333)
_LCC_LAT0 = math.radians(41.6666666666667)
_LCC_LON0 = math.radians(-120.5)
_LCC_FE_M = 4921259.843 * _INTL_FOOT_M  # 1_500_000 m exactly
_LCC_FN_M = 0.0


def _lcc_small_m(lat):
    return math.cos(lat) / math.sqrt(1.0 - _E2 * math.sin(lat) ** 2)


def _lcc_small_t(lat):
    sin_lat = _E * math.sin(lat)
    return math.tan(math.pi / 4.0 - lat / 2.0) / (
        ((1.0 - sin_lat) / (1.0 + sin_lat)) ** (_E / 2.0)
    )


_M1 = _lcc_small_m(_LCC_LAT1)
_M2 = _lcc_small_m(_LCC_LAT2)
_T0 = _lcc_small_t(_LCC_LAT0)
_T1 = _lcc_small_t(_LCC_LAT1)
_T2 = _lcc_small_t(_LCC_LAT2)
_LCC_N = (math.log(_M1) - math.log(_M2)) / (math.log(_T1) - math.log(_T2))
_LCC_BIG_F = _M1 / (_LCC_N * _T1 ** _LCC_N)
_LCC_RHO0 = _A * _LCC_BIG_F * _T0 ** _LCC_N

# --- Transverse Mercator: UTM Zone 10N ---
_UTM_K0 = 0.9996
_UTM_LON0 = math.radians(-123.0)
_UTM_FE_M = 500000.0
_UTM_FN_M = 0.0
_EP2 = _E2 / (1.0 - _E2)


def stateplane_or_south_ift_to_latlon(x_ft, y_ft):
    """Oregon South State Plane (International feet) -> (lat_deg, lon_deg)."""
    easting = x_ft * _INTL_FOOT_M - _LCC_FE_M
    northing = y_ft * _INTL_FOOT_M - _LCC_FN_M

    rho = math.copysign(
        math.sqrt(easting ** 2 + (_LCC_RHO0 - northing) ** 2), _LCC_N
    )
    t = (rho / (_A * _LCC_BIG_F)) ** (1.0 / _LCC_N)
    theta = math.atan2(easting, _LCC_RHO0 - northing)
    lon = theta / _LCC_N + _LCC_LON0

    lat = math.pi / 2.0 - 2.0 * math.atan(t)
    for _ in range(8):  # converges well inside 8 iterations at this latitude
        sin_lat = _E * math.sin(lat)
        lat = math.pi / 2.0 - 2.0 * math.atan(
            t * (((1.0 - sin_lat) / (1.0 + sin_lat)) ** (_E / 2.0))
        )
    return math.degrees(lat), math.degrees(lon)


def latlon_to_utm10n(lat_deg, lon_deg):
    """(lat_deg, lon_deg) -> (x_m, y_m) in WGS84 UTM Zone 10N."""
    lat = math.radians(lat_deg)
    lon = math.radians(lon_deg)

    nu = _A / math.sqrt(1.0 - _E2 * math.sin(lat) ** 2)
    t = math.tan(lat) ** 2
    c = _EP2 * math.cos(lat) ** 2
    a = (lon - _UTM_LON0) * math.cos(lat)
    m = _A * (
        (1.0 - _E2 / 4.0 - 3.0 * _E2 ** 2 / 64.0 - 5.0 * _E2 ** 3 / 256.0) * lat
        - (3.0 * _E2 / 8.0 + 3.0 * _E2 ** 2 / 32.0 + 45.0 * _E2 ** 3 / 1024.0)
        * math.sin(2.0 * lat)
        + (15.0 * _E2 ** 2 / 256.0 + 45.0 * _E2 ** 3 / 1024.0) * math.sin(4.0 * lat)
        - (35.0 * _E2 ** 3 / 3072.0) * math.sin(6.0 * lat)
    )

    x = _UTM_K0 * nu * (
        a
        + (1.0 - t + c) * a ** 3 / 6.0
        + (5.0 - 18.0 * t + t ** 2 + 72.0 * c - 58.0 * _EP2) * a ** 5 / 120.0
    ) + _UTM_FE_M
    y = _UTM_K0 * (
        m
        + nu * math.tan(lat) * (
            a ** 2 / 2.0
            + (5.0 - t + 9.0 * c + 4.0 * c ** 2) * a ** 4 / 24.0
            + (61.0 - 58.0 * t + t ** 2 + 600.0 * c - 330.0 * _EP2) * a ** 6 / 720.0
        )
    ) + _UTM_FN_M
    return x, y


def stateplane_or_south_ift_to_utm10n(x_ft, y_ft):
    """Oregon South State Plane (International feet) -> UTM 10N meters."""
    lat_deg, lon_deg = stateplane_or_south_ift_to_latlon(x_ft, y_ft)
    return latlon_to_utm10n(lat_deg, lon_deg)
