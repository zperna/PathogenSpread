"""
Multi-generation what-if spread simulation on a tree inventory.

Iterates spread_engine._infection_hazard with a growing infected set: each
generation, every still-susceptible tree whose single-step hazard reaches
the pathogen's spread_step.promotion_threshold flips to infected and acts
as a source in the next generation. Deterministic -- one reproducible
trajectory, not a probability field.

This is an illustrative scenario, not a dated or validated forecast. A
"generation" is an abstract dispersal cycle, not a season or a year.
There is no calibration; the threshold and the generation count are knobs
to sweep. See docs/feature_contracts/temporal_spread_per_tree.md.
"""

import pandas as pd

from spread_engine import _infection_hazard

STALL_CAP = 25  # hard ceiling when n_steps is not given -- see design note


def simulate_spread(inventory, pathogen_config, environment=None, wind=None,
                    n_steps=None, seed=None):
    """
    Parameters
    ----------
    inventory : DataFrame with columns x, y, species, stress_index,
        infected (the infected rows are the initial known cases).
    pathogen_config : a dict from pathogens.PATHOGENS -- must include a
        spread_step block.
    environment, wind : as spread_engine.compute_risk.
    n_steps : generations to run. None = run until a generation infects
        nothing, capped at STALL_CAP.
    seed : accepted but unused -- reserved for a future stochastic mode
        so its addition will not change this signature.

    Returns
    -------
    (result, log)
    result : the inventory (index reset) plus
        is_initial_case  : bool
        infected_at_step  : 0 for initial cases, t for a tree promoted in
            generation t, pd.NA if never promoted in the run
        risk_at_infection : the hazard that cleared the threshold, pd.NA
            if never promoted
        infected           : bool, True for every tree infected by the end
    log : list of {step, newly_infected: [tree_id, ...],
        cumulative_infected} -- one entry per generation actually run,
        including a final entry for the generation that stalled.
    """
    if "spread_step" not in pathogen_config:
        raise ValueError(
            f"pathogen_config for {pathogen_config.get('display_name', '?')} has no "
            "'spread_step' block; simulate_spread cannot run (see pathogens.py)"
        )
    threshold = pathogen_config["spread_step"]["promotion_threshold"]

    df = inventory.copy().reset_index(drop=True)
    df["infected"] = df["infected"].astype(bool)
    df["is_initial_case"] = df["infected"]
    df["infected_at_step"] = pd.NA
    df.loc[df["infected"], "infected_at_step"] = 0
    df["risk_at_infection"] = pd.NA

    cap = STALL_CAP if n_steps is None else n_steps
    log = []
    for step in range(1, cap + 1):
        sources = df[df["infected"]]
        targets = df[~df["infected"]]
        if sources.empty or targets.empty:
            break

        risk, _ = _infection_hazard(
            sources[["x", "y"]].to_numpy(), targets, pathogen_config, environment, wind
        )
        promoted = targets.index[risk >= threshold]

        if len(promoted) == 0:
            log.append({"step": step, "newly_infected": [],
                        "cumulative_infected": int(df["infected"].sum())})
            break

        df.loc[promoted, "infected"] = True
        df.loc[promoted, "infected_at_step"] = step
        df.loc[promoted, "risk_at_infection"] = risk[risk >= threshold]
        log.append({
            "step": step,
            "newly_infected": df.loc[promoted, "tree_id"].tolist(),
            "cumulative_infected": int(df["infected"].sum()),
        })

    return df, log
