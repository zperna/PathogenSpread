"""
Generates a synthetic tree inventory so the spread engine can be tested
before real field data exists. Swap this out for a real inventory (CSV,
shapefile, Field Maps export, etc.) later -- the engine just needs a
DataFrame with these columns:

    tree_id, x, y, species, dbh_in, stress_index, infected

x/y are in meters on a local projected grid (not lat/lon) so distance
math is straightforward. When you bring in real data, project it to a
local UTM zone or state plane first.

stress_index: 0-1, where 1.0 = highly stressed (drought, compaction,
    root damage, etc.) -- this is exactly the kind of field observation
    an arborist doing canopy work is well positioned to log.
"""

import numpy as np
import pandas as pd

SPECIES_POOL = [
    "oregon_ash", "oak", "maple", "douglas_fir",
    "western_hemlock", "pine", "sycamore", "dogwood", "green_ash",
]


def generate_inventory(n_trees=400, area_size_m=2000, n_index_cases=3, seed=42):
    """
    Creates a random tree inventory scattered over a square area,
    with a handful of trees marked as initial infection sources
    ("index cases") to seed the spread simulation.
    """
    rng = np.random.default_rng(seed)

    df = pd.DataFrame({
        "tree_id": [f"T{i:04d}" for i in range(n_trees)],
        "x": rng.uniform(0, area_size_m, n_trees),
        "y": rng.uniform(0, area_size_m, n_trees),
        "species": rng.choice(SPECIES_POOL, n_trees),
        "dbh_in": np.round(rng.uniform(4, 36, n_trees), 1),
        "stress_index": np.round(rng.beta(2, 5, n_trees), 2),  # skewed toward low stress
        "infected": False,
    })

    # seed a small cluster of index cases so the map has a clear origin point
    index_ids = rng.choice(df.index, n_index_cases, replace=False)
    df.loc[index_ids, "infected"] = True

    return df


def generate_douglas_fir_grove_inventory(
    n_trees=120,
    area_size_m=1200,
    n_index_cases=4,
    seed=11,
):
    """
    Creates a Douglas-fir-dominated grove scenario with a small set of
    initial infected trees, suitable for the red ring rot prototype.
    """
    rng = np.random.default_rng(seed)
    center = area_size_m / 2
    cluster_scale = area_size_m * 0.22

    x = rng.normal(center, cluster_scale * 0.22, n_trees)
    y = rng.normal(center, cluster_scale * 0.22, n_trees)
    x = np.clip(x, 0, area_size_m)
    y = np.clip(y, 0, area_size_m)

    species_choices = np.array(["douglas_fir", "western_hemlock", "pine", "oak", "maple"])
    species_weights = np.array([0.78, 0.10, 0.07, 0.03, 0.02])
    species = rng.choice(species_choices, size=n_trees, p=species_weights)

    df = pd.DataFrame({
        "tree_id": [f"DG{i:03d}" for i in range(n_trees)],
        "x": np.round(x, 1),
        "y": np.round(y, 1),
        "species": species,
        "dbh_in": np.round(rng.uniform(8, 32, n_trees), 1),
        "stress_index": np.round(rng.beta(2, 3, n_trees), 2),
        "infected": False,
    })

    center_distance = np.sqrt((df["x"] - center) ** 2 + (df["y"] - center) ** 2)
    infected_candidates = np.argsort(center_distance)[: max(3, n_index_cases)]

    if len(infected_candidates) > 0:
        infected_targets = infected_candidates[:n_index_cases]
        df.loc[infected_targets, "infected"] = True
        df.loc[infected_targets, "species"] = "douglas_fir"

    return df


def generate_environment_grid(area_size_m=2000, resolution_m=50, seed=7):
    """
    Creates a simple synthetic environmental raster: normalized 0-1
    'moisture' and 'temp_suitability' surfaces. Placeholder for real
    Daymet/soils data pulled the same way you did in GEOG 562.
    """
    rng = np.random.default_rng(seed)
    n = int(area_size_m / resolution_m)

    # smooth-ish random fields via simple blurring so it doesn't look like noise
    from scipy.ndimage import gaussian_filter
    moisture = gaussian_filter(rng.random((n, n)), sigma=3)
    temp = gaussian_filter(rng.random((n, n)), sigma=3)

    moisture = (moisture - moisture.min()) / (moisture.max() - moisture.min())
    temp = (temp - temp.min()) / (temp.max() - temp.min())

    return {
        "moisture": moisture,
        "temp": temp,
        "resolution_m": resolution_m,
        "area_size_m": area_size_m,
    }
