"""
Generic pathogen spread engine.

One engine, tunable per pathogen via the config dicts in pathogens.py.
For each non-infected tree, risk is built from four factors multiplied
together:

    risk = dispersal_kernel(distance_to_nearest_source)
           * host_susceptibility(species)
           * environmental_match(location)
           * stress_amplification(tree's stress_index)

This is a simple, explainable first-pass model. It is good enough for
field risk flagging and easy to explain and defend. It is not a
publication-grade epidemiological model. Treat it as a scaffold that
can be replaced in parts. For example, swap the exponential kernel for
a dispersal function fit to real outbreak data when you have that data.
"""

import numpy as np
import pandas as pd


def _distance_matrix(sources_xy, targets_xy):
    """Euclidean distance (meters) from each target to each source."""
    diff = targets_xy[:, None, :] - sources_xy[None, :, :]
    return np.sqrt((diff ** 2).sum(axis=2))


def _bearing_matrix(sources_xy, targets_xy):
    """Compass bearing (degrees, 0=north/90=east, clockwise) from each
    source to each target. It has the same shape as _distance_matrix.
    It uses the convention of IEM wind rose directions (see
    fetch_wind_rose.py)."""
    diff = targets_xy[:, None, :] - sources_xy[None, :, :]
    dx, dy = diff[..., 0], diff[..., 1]
    return np.degrees(np.arctan2(dx, dy)) % 360


def _dispersal_kernel(distance_m, decay_rate, max_dispersal_m, bearing_deg=None, wind_bias=None):
    """
    Exponential decay kernel, hard-capped at max_dispersal_distance.
    At distance 0, the risk contribution is 1.0. Beyond max_dispersal,
    it is 0.

    When bearing_deg (source-to-target compass bearing, from
    _bearing_matrix) and wind_bias are both given, the decay rate is
    adjusted for each target. wind_bias is a {prevailing_direction_deg,
    directionality_strength} dict, for example loaded from a site's
    wind_rose.json. Targets downwind of a source decay more slowly, so
    they reach farther. Targets upwind decay faster, so they reach less
    far. directionality_strength sets the blend. 0 means no change
    (isotropic). 1 means the full effect. This replaces the plain
    isotropic call in that case. See
    docs/feature_contracts/wind_dispersal_and_soil_reweight.md Part B.
    prevailing_direction_deg is the direction the wind blows FROM
    (standard meteorological convention, matching IEM). So downwind is
    +180 deg.
    """
    if bearing_deg is not None and wind_bias is not None:
        downwind_deg = (wind_bias["prevailing_direction_deg"] + 180) % 360
        alignment = np.cos(np.radians(bearing_deg - downwind_deg))
        effective_decay_rate = decay_rate * (1 - wind_bias["directionality_strength"] * alignment)
    else:
        effective_decay_rate = decay_rate

    kernel = np.exp(-effective_decay_rate * distance_m)
    kernel = np.where(distance_m > max_dispersal_m, 0.0, kernel)
    return kernel


def _sample_grid_at_points(grid, resolution_m, xy, origin_x=0.0, origin_y=0.0):
    """
    Nearest-neighbor lookup of a raster value at given x,y points.

    origin_x and origin_y are the real-world coordinates of the grid's
    row-0 and col-0 cell. The default is 0,0, which suits the synthetic
    local-grid surfaces. Arrays are assumed bottom-up (row 0 = origin_y).
    This matches what PathogenPy/arcpy_export/export_site_layers.py writes.
    """
    n_rows, n_cols = grid.shape
    col = np.clip(((xy[:, 0] - origin_x) / resolution_m).astype(int), 0, n_cols - 1)
    row = np.clip(((xy[:, 1] - origin_y) / resolution_m).astype(int), 0, n_rows - 1)
    return grid[row, col]


def _combine_spatial_environment(pathogen_config: dict, environment: dict, target_xy: np.ndarray):
    """Combine several raster-derived suitability surfaces into one score."""
    triggers = pathogen_config.get("spatial_weights")
    if triggers is None:
        return None

    origin_x = environment.get("origin_x", 0.0)
    origin_y = environment.get("origin_y", 0.0)

    weighted_values = []
    total_weight = 0.0
    for surface_name, weight in triggers.items():
        if surface_name not in environment:
            continue
        surface = environment[surface_name]
        values = _sample_grid_at_points(surface, environment["resolution_m"], target_xy, origin_x, origin_y)
        weighted_values.append(values * weight)
        total_weight += weight

    if total_weight <= 0 or not weighted_values:
        return None

    return np.sum(weighted_values, axis=0) / total_weight


def _infection_hazard(source_xy, targets, pathogen_config, environment=None, wind=None):
    """
    Per-step infection hazard (0-1) for a set of currently-susceptible
    trees, given a set of currently-infected source points. This is the
    single-step core of compute_risk. It is a separate function so
    spread_simulation.simulate_spread can run it again with a growing
    source set. The math is not repeated. See
    docs/feature_contracts/temporal_spread_per_tree.md.

    Parameters
    ----------
    source_xy : (n_sources, 2) array of infected-tree coordinates.
    targets : DataFrame of the susceptible trees. It needs x, y, species,
        and stress_index. Its row order defines the output order.
    pathogen_config, environment, wind : as compute_risk.

    Returns
    -------
    (risk, components). risk is a 0-1 array (len == len(targets)).
    components is a dict of the dispersal_score, susceptibility,
    environmental_match, and stress_amplification arrays. These arrays
    multiply together to make risk.
    """
    target_xy = targets[["x", "y"]].to_numpy()

    dist = _distance_matrix(source_xy, target_xy)  # shape (n_targets, n_sources)
    bearing = None
    if wind is not None and pathogen_config.get("transmission_mode") in ("airborne", "vector"):
        bearing = _bearing_matrix(source_xy, target_xy)
    kernel = _dispersal_kernel(
        dist,
        decay_rate=pathogen_config["decay_rate"],
        max_dispersal_m=pathogen_config["max_dispersal_distance_m"],
        bearing_deg=bearing,
        wind_bias=wind,
    )
    # Risk comes from the nearest or strongest source, not from the sum of
    # all sources. This avoids unrealistic stacking when many sources are
    # far away.
    dispersal_score = kernel.max(axis=1)

    # host susceptibility
    susceptibility = targets["species"].map(
        lambda sp: pathogen_config["host_susceptibility"].get(sp, 0.0)
    ).to_numpy()

    # environmental match
    env_match = None
    if environment is not None:
        env_match = _combine_spatial_environment(pathogen_config, environment, target_xy)
        if env_match is None:
            origin_x = environment.get("origin_x", 0.0)
            origin_y = environment.get("origin_y", 0.0)
            moisture = _sample_grid_at_points(
                environment["moisture"], environment["resolution_m"], target_xy, origin_x, origin_y,
            )
            temp = _sample_grid_at_points(
                environment["temp"], environment["resolution_m"], target_xy, origin_x, origin_y,
            )
            trig = pathogen_config["environmental_triggers"]
            env_match = (
                moisture * trig["moisture_weight"] + temp * trig["temp_weight"]
            ) / (trig["moisture_weight"] + trig["temp_weight"])
    if env_match is None:
        env_match = np.full(len(targets), 0.5)

    # stress amplification. This scales risk up for stressed trees.
    # The result is capped so it does not pass 1.0 downstream.
    stress_amp = 1 + (pathogen_config["stress_multiplier"] - 1) * targets["stress_index"].to_numpy()

    risk = np.clip(dispersal_score * susceptibility * env_match * stress_amp, 0, 1)
    return risk, {
        "dispersal_score": dispersal_score,
        "susceptibility": susceptibility,
        "environmental_match": env_match,
        "stress_amplification": stress_amp,
    }


def compute_risk(inventory: pd.DataFrame, pathogen_config: dict, environment: dict = None, wind: dict = None):
    """
    Computes a 0-1 risk score for every non-infected tree in the inventory.

    Parameters
    ----------
    inventory : DataFrame with columns x, y, species, stress_index, infected
    pathogen_config : one of the dicts from pathogens.PATHOGENS
    environment : optional dict from synthetic_data.generate_environment_grid
        (or real raster data in the same shape). If omitted, environmental
        match defaults to a neutral 0.5 for every tree.
    wind : optional {prevailing_direction_deg, directionality_strength} dict
        (e.g. loaded from a site's wind_rose.json). It is only applied when
        pathogen_config["transmission_mode"] is "airborne" or "vector".
        See _dispersal_kernel and docs/feature_contracts/
        wind_dispersal_and_soil_reweight.md Part B.

    Returns
    -------
    DataFrame: the original inventory plus a 'risk_score' column. Trees that
    are already infected get 0. They are the source, not an at-risk tree.
    """
    df = inventory.copy()
    sources = df[df["infected"]]
    targets = df[~df["infected"]]

    if sources.empty or targets.empty:
        df["risk_score"] = 0.0
        return df

    risk, components = _infection_hazard(
        sources[["x", "y"]].to_numpy(), targets, pathogen_config, environment, wind
    )

    df["risk_score"] = 0.0
    df["dispersal_score"] = 0.0
    df["susceptibility"] = 0.0
    df["environmental_match"] = 0.0
    df["stress_amplification"] = 1.0

    df.loc[targets.index, "risk_score"] = risk
    df.loc[targets.index, "dispersal_score"] = components["dispersal_score"]
    df.loc[targets.index, "susceptibility"] = components["susceptibility"]
    df.loc[targets.index, "environmental_match"] = components["environmental_match"]
    df.loc[targets.index, "stress_amplification"] = components["stress_amplification"]

    return df


def compute_risk_raster(pathogen_config: dict, environment: dict, source_xy: np.ndarray, wind: dict = None):
    """
    Computes a 0-1 site-suitability risk surface for every cell of the
    environment grid, given known infection source point(s), instead of
    per-tree risk scores.

    risk_cell = dispersal_kernel(distance to nearest source) * environmental_match(cell)

    There is no per-cell species or stress_index. So, unlike compute_risk,
    this function leaves out host susceptibility and stress amplification
    on purpose. See docs/feature_contracts/real_site_risk_raster.md's
    Non-goals. This answers "how favorable is this location for spread from
    the known source(s)," not "which specific trees are at risk."

    Parameters
    ----------
    pathogen_config : one of the dicts from pathogens.PATHOGENS. It must
        define spatial_weights naming at least one surface present in
        environment.
    environment : dict from spatial_inputs.load_site_grid (or
        synthetic_data.generate_environment_grid). It must include
        resolution_m and at least one of pathogen_config["spatial_weights"]'s
        surfaces. Those surfaces define the raster's shape.
    source_xy : (n_sources, 2) array of known infection point coordinates,
        in the same real-world units as environment's origin_x/origin_y.
    wind : optional {prevailing_direction_deg, directionality_strength} dict
        (e.g. loaded from a site's wind_rose.json). It is only applied when
        pathogen_config["transmission_mode"] is "airborne" or "vector".
        See _dispersal_kernel and docs/feature_contracts/
        wind_dispersal_and_soil_reweight.md Part B.

    Returns
    -------
    2D numpy array, shape (n_rows, n_cols), bottom-up (row 0 = origin_y).
    It uses the same row convention as the arrays that load_site_grid reads.
    """
    spatial_weights = pathogen_config.get("spatial_weights", {})
    reference_surface = next(
        (environment[name] for name in spatial_weights if name in environment), None
    )
    if reference_surface is None:
        raise ValueError(
            "environment must include at least one of pathogen_config['spatial_weights'] "
            "to define the raster grid shape"
        )

    resolution_m = environment["resolution_m"]
    origin_x = environment.get("origin_x", 0.0)
    origin_y = environment.get("origin_y", 0.0)
    n_rows, n_cols = reference_surface.shape

    cell_x = origin_x + (np.arange(n_cols) + 0.5) * resolution_m
    cell_y = origin_y + (np.arange(n_rows) + 0.5) * resolution_m
    grid_x, grid_y = np.meshgrid(cell_x, cell_y)
    cell_xy = np.column_stack([grid_x.ravel(), grid_y.ravel()])

    dist = _distance_matrix(source_xy, cell_xy)
    bearing = None
    if wind is not None and pathogen_config.get("transmission_mode") in ("airborne", "vector"):
        bearing = _bearing_matrix(source_xy, cell_xy)
    kernel = _dispersal_kernel(
        dist,
        decay_rate=pathogen_config["decay_rate"],
        max_dispersal_m=pathogen_config["max_dispersal_distance_m"],
        bearing_deg=bearing,
        wind_bias=wind,
    )
    dispersal_score = kernel.max(axis=1)

    env_match = _combine_spatial_environment(pathogen_config, environment, cell_xy)
    if env_match is None:
        env_match = np.full(cell_xy.shape[0], 0.5)

    risk = np.clip(dispersal_score * env_match, 0, 1)
    return risk.reshape(n_rows, n_cols)
