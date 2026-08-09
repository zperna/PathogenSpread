"""Spatial input helpers for pathogen risk modeling.

This module provides functions to turn raster layers into normalized
suitability surfaces, generate synthetic stand-in surfaces for a
proof-of-concept spatial prototype, and load the real site grid exported
by PathogenPy/arcpy_export/export_site_layers.py (see
docs/notes/real_site_risk_raster.md for why that export is a separate
arcpy step rather than a dependency of this module).
"""

import json
from pathlib import Path

import numpy as np
import pandas as pd

try:
    import rasterio
except ImportError:  # pragma: no cover
    rasterio = None


# NLCD 2016 class codes -> suitability score. A domain-judgment placeholder,
# same spirit as the synthetic land_cover_scores below: denser forest cover
# is more favorable to a canopy-to-canopy airborne fungal pathogen, developed
# and open surfaces are not.
NLCD_SCORE_MAP = {
    11: 0.0,   # open water
    21: 0.3,   # developed, open space
    22: 0.2,   # developed, low intensity
    23: 0.1,   # developed, medium intensity
    24: 0.05,  # developed, high intensity
    31: 0.1,   # barren land
    41: 0.6,   # deciduous forest
    42: 0.9,   # evergreen forest
    43: 0.8,   # mixed forest
    52: 0.4,   # shrub/scrub
    71: 0.3,   # grassland/herbaceous
    81: 0.2,   # pasture/hay
    82: 0.15,  # cultivated crops
    90: 0.85,  # woody wetlands
    95: 0.7,   # emergent herbaceous wetlands
}

# USDA dominant drainage class -> suitability score. Wetter classes score
# higher, consistent with red_ring_rot's moisture_weight assumption and the
# synthetic soil_scores placeholder it replaces. Ordinal domain judgment,
# not a validated pathology mapping.
DRAINAGE_CLASS_SCORES = {
    "Excessively drained": 0.15,
    "Somewhat excessively drained": 0.25,
    "Well drained": 0.35,
    "Moderately well drained": 0.55,
    "Somewhat poorly drained": 0.75,
    "Poorly drained": 0.90,
    "Very poorly drained": 1.00,
}


def normalize_surface(surface, min_value=None, max_value=None):
    """Normalize a surface array to 0-1 based on optional bounds."""
    arr = np.asarray(surface, dtype=float)
    if min_value is None:
        min_value = arr.min()
    if max_value is None:
        max_value = arr.max()
    if max_value == min_value:
        return np.zeros_like(arr)
    normalized = (arr - min_value) / (max_value - min_value)
    return np.clip(normalized, 0.0, 1.0)


def score_categorical_surface(categorical_raster, score_map, default=0.0):
    """Map categorical raster codes to a normalized suitability surface."""
    raster = np.asarray(categorical_raster)
    scored = np.full(raster.shape, default, dtype=float)
    for category, score in score_map.items():
        scored[raster == category] = score
    return normalize_surface(scored, 0.0, 1.0)


def load_raster(path):
    """Load a raster as a numpy array using rasterio, if available."""
    if rasterio is None:
        raise ImportError("rasterio is required to load real raster files")
    with rasterio.open(path) as src:
        array = src.read(1)
        transform = src.transform
        crs = src.crs
    return array, transform, crs


def generate_synthetic_spatial_surfaces(area_size_m=1200, resolution_m=50, seed=17):
    """Generate synthetic spatial suitability layers for prototype testing."""
    rng = np.random.default_rng(seed)
    n = int(area_size_m / resolution_m)

    from scipy.ndimage import gaussian_filter

    moisture = gaussian_filter(rng.random((n, n)), sigma=3)
    temp = gaussian_filter(rng.random((n, n)), sigma=4)
    terrain = gaussian_filter(rng.random((n, n)), sigma=2)
    land_cover_raw = gaussian_filter(rng.random((n, n)), sigma=5)
    soil_raw = gaussian_filter(rng.random((n, n)), sigma=5)

    moisture = normalize_surface(moisture)
    temp = normalize_surface(temp)
    terrain = normalize_surface(terrain)

    # Land cover is categorized so the prototype can simulate habitat suitability.
    land_cover_codes = np.digitize(land_cover_raw, bins=[0.2, 0.4, 0.6, 0.8]) + 1
    land_cover_scores = {
        1: 0.2,  # developed / low-risk
        2: 0.5,  # open ground
        3: 0.7,  # mixed forest
        4: 0.9,  # dense forest
        5: 0.8,  # wet forest / riparian
    }
    land_cover = score_categorical_surface(land_cover_codes, land_cover_scores)

    soil_codes = np.digitize(soil_raw, bins=[0.25, 0.5, 0.75]) + 1
    soil_scores = {
        1: 0.3,  # very well drained
        2: 0.5,  # moderate drainage
        3: 0.75, # seasonally wet
        4: 0.95, # poorly drained / saturated
    }
    soil = score_categorical_surface(soil_codes, soil_scores)

    return {
        "area_size_m": area_size_m,
        "resolution_m": resolution_m,
        "moisture": moisture,
        "temp": temp,
        "terrain": terrain,
        "land_cover": land_cover,
        "land_cover_codes": land_cover_codes,
        "soil": soil,
        "soil_codes": soil_codes,
    }


def sample_surface_at_points(surface, area_size_m, resolution_m, xy):
    """Nearest-neighbor lookup for any surface at given x,y points."""
    n = surface.shape[0]
    col = np.clip((xy[:, 0] / area_size_m * n).astype(int), 0, n - 1)
    row = np.clip((xy[:, 1] / area_size_m * n).astype(int), 0, n - 1)
    return surface[row, col]


def score_terrain(slope_degrees, aspect_degrees):
    """
    Simple, documented placeholder terrain suitability (0-1) from slope and
    aspect: moderate slope (more moisture retention than steep, well-drained
    ground) and north-facing aspect (cooler, damper) score higher. Not a
    validated forest pathology model -- see docs/notes/real_site_risk_raster.md.

    arcpy.sa.Aspect returns -1 for flat cells (slope == 0); those are treated
    as aspect-neutral (0.5) rather than propagating -1 into the cosine math.
    """
    slope_score = np.clip(1 - np.abs(slope_degrees - 15) / 30, 0.0, 1.0)

    aspect_score = (1 + np.cos(np.radians(aspect_degrees))) / 2
    aspect_score = np.where(aspect_degrees < 0, 0.5, aspect_score)

    return (slope_score + aspect_score) / 2


def load_site_grid(data_dir):
    """
    Loads the real site grid exported by
    PathogenPy/arcpy_export/export_site_layers.py into the same environment
    dict shape compute_risk/compute_risk_raster expect, with land_cover and
    soil already converted from raw codes to 0-1 suitability scores.
    """
    data_dir = Path(data_dir)

    with open(data_dir / "grid_meta.json") as f:
        meta = json.load(f)
    with open(data_dir / "drainage_classes.json") as f:
        drainage_classes = {int(code): name for code, name in json.load(f).items()}

    landcover_codes = np.load(data_dir / "landcover.npy")
    soil_codes = np.load(data_dir / "soil_drain_code.npy")
    slope_degrees = np.load(data_dir / "slope_degrees.npy")
    aspect_degrees = np.load(data_dir / "aspect_degrees.npy")

    land_cover = score_categorical_surface(landcover_codes, NLCD_SCORE_MAP)

    drainage_score_by_code = {
        code: DRAINAGE_CLASS_SCORES.get(name, 0.0) for code, name in drainage_classes.items()
    }
    soil = score_categorical_surface(soil_codes, drainage_score_by_code)

    terrain = score_terrain(slope_degrees, aspect_degrees)

    return {
        "area_size_m": meta["area_size_m"],
        "resolution_m": meta["resolution_m"],
        "origin_x": meta["origin_x"],
        "origin_y": meta["origin_y"],
        "land_cover": land_cover,
        "soil": soil,
        "terrain": terrain,
    }


def load_known_cases(csv_path):
    """Loads known_cases.csv (written by export_site_layers.py) as a DataFrame."""
    df = pd.read_csv(csv_path)
    df["infected"] = df["infected"].astype(bool)
    return df
