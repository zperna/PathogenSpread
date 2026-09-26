# Feature contract: emerald ash borer spatial_weights (config only)

## Status
Config-only, by the user's choice. No real EAB case exists yet, so this
does not build a real site. It closes the config gap so a real site can
be wired in later the same way `anthracnose` was
(`docs/feature_contracts/anthracnose_site_risk.md`), the moment a
confirmed case exists.

## Problem
`emerald_ash_borer` is the one pathogen in `pathogens.py` with no
`spatial_weights` block. `compute_risk_raster` requires at least one
`spatial_weights` surface present in the environment to define the
raster's shape, so it cannot run for this pathogen at all today, real
site or synthetic. `compute_risk` falls back to the
`environmental_triggers` moisture/temp path when `spatial_weights` is
absent, which works against `synthetic_data.generate_environment_grid`
but would `KeyError` against `spatial_inputs.load_site_grid` (real
sites), which has no `moisture`/`temp` keys -- see the same caveat
already recorded in
`docs/notes/site_tree_host_inventory.md`'s Assumptions.

The POS integration makes this newly worth doing even without a real
case: `Fraxinus` (ash) is well represented at every existing site
(`site` 214, `site_phytophthora` 152, `site_anthracnose` 173 trees,
oregon_ash + green_ash combined) -- see
`docs/feature_contracts/site_tree_host_inventory.md`'s Verification.

## Goal
Give `emerald_ash_borer` a `spatial_weights` block reasoned through its
own transmission biology, not copied from another pathogen, so it is
ready to run the moment a real case exists. Verify what can be verified
without one: that the math runs and that the new surfaces visibly
change the result, against synthetic data.

## Scope
1. **`pathogens.py`: add `emerald_ash_borer["spatial_weights"]`.**
   EAB is vector/flight-based (adult beetles fly to find ash, larvae
   bore under bark), not wind/rain-dispersed and not root-contact -- a
   third mechanism distinct from every pathogen that already has a
   `spatial_weights` block:
   - `land_cover` (0.7): the beetle still needs an actual tree canopy
     to land in and colonize at the site it reaches, the same
     "host/canopy density" role `land_cover` already plays for the
     other three pathogens.
   - `wetness` (0.3), the DEM-derived topographic wetness index (see
     `docs/feature_contracts/topographic_wetness_index.md`): a
     **host-habitat proxy**, not a moisture-triggers-infection
     mechanism. Oregon ash (`Fraxinus latifolia`) is characteristically
     a wetland/riparian species in the Willamette Valley, so higher TWI
     is a proxy for "more likely ash habitat," a different causal claim
     from `phytophthora`'s use of the same surface (root-zone moisture
     triggering infection). Reusing `wetness` here is not the mistake
     `wind_dispersal_and_soil_reweight.md` warned against (copying a
     surface without reasoning through it) -- it is the same surface
     doing a different, stated job.
   - `exposure`/`terrain`/`soil` deliberately left out: no wind-exposure
     wound-infection pathway (unlike `red_ring_rot`), no root contact
     (unlike `phytophthora`).
   - `environmental_triggers` (`temp_weight`/`moisture_weight`) stays in
     the config, now superseded for the real-site path once
     `spatial_weights` is set -- the same non-authoritative-but-kept
     pattern already true for the other three pathogens. A comment
     notes this, matching `red_ring_rot`'s existing comment style.
2. **No other file changes.** No `export_site_layers.py` `CASE_LAYERS`
   entry, no `run_real_site_risk_raster.py` / `run_real_site_tree_risk.py`
   / `run_real_site_tree_spread.py` `RUNS` entry, no `data/site_eab/`.
   All deferred to a follow-on contract once a real case exists.

## Inputs
- `pathogens.py`'s existing `emerald_ash_borer` config (transmission
  mode, dispersal constants, host susceptibility, stress multiplier --
  all unchanged).
- Synthetic data only for verification:
  `synthetic_data.generate_inventory` (species pool includes
  `oregon_ash`/`green_ash`) and
  `spatial_inputs.generate_synthetic_spatial_surfaces` (has
  `land_cover`; no `wetness` -- see Non-goals).

## Outputs
- Updated `pathogens.py`.
- This contract, a design note, verification recorded here or in the
  design note.

## Success criteria
1. `compute_risk` runs for `emerald_ash_borer` against a synthetic
   inventory + `generate_synthetic_spatial_surfaces` without error.
2. The `environmental_match` column visibly differs from a run with
   `spatial_weights` removed (confirms `land_cover` actually
   participates, not just that the code path is silently falling back).
3. The other three pathogens' behavior is unchanged (regression:
   `run_real_site_risk_raster.py`, `run_real_site_tree_risk.py`,
   `run_real_site_tree_spread.py` all diff clean).
4. The reasoning for `land_cover` + `wetness` is written down distinctly
   from `anthracnose`'s use of the same two surfaces, so a future reader
   does not mistake this for a copy-paste.

## Non-goals
1. **No real site.** No known-case feature class, no `data/site_eab/`,
   no raster or per-tree run against real data. This is the whole point
   of the "config only" choice -- deferred to a follow-on contract.
2. **`wetness`'s contribution is not verified end to end.**
   `generate_synthetic_spatial_surfaces` has no `wetness` key, so in the
   synthetic verification run, `_combine_spatial_environment` silently
   drops it (`if surface_name not in environment: continue`) and
   renormalizes -- only `land_cover` is actually exercised. The
   `wetness` half of this reasoning is confirmed only once a real EAB
   site's `load_site_grid` output (which does have `wetness`) is
   available. Recorded, not worked around with a synthetic surface that
   would just be another placeholder.
3. **`max_dispersal_distance_m` (3,000 m) exceeds the current AOI
   convention.** Every existing site is a 2 km square
   (`AOI_HALF_SIZE_M = 1000` in `export_site_layers.py`). If a real EAB
   site is ever built the same way, the dispersal kernel would
   essentially never reach its cap within the AOI. Flagged for whoever
   writes that follow-on contract; not addressed here.
4. No validation against real EAB pathology literature. Domain-judgment
   weights, same caveat as every other pathogen's `spatial_weights`.

## Definition of done
1. This contract exists (done).
2. No separate design note -- the reasoning is fully captured in Scope
   above; verification recorded directly here, proportionate to a
   config-only change.
3. `pathogens.py` updated (done).
4. Synthetic verification run and recorded (done, 2026-09-11).
5. Regression on the three real-site pathogens confirmed clean (done,
   2026-09-11).

## Verification (2026-09-11)

### Synthetic run -- PASS
`compute_risk` against `synthetic_data.generate_inventory(area_size_m=
1200, n_trees=300)` (species pool includes `oregon_ash`/`green_ash`, 64
ash trees in the seeded run) and
`spatial_inputs.generate_synthetic_spatial_surfaces(area_size_m=1200)`
(has `land_cover`; no `wetness`, see Non-goals):
- Ran without error for all 297 non-infected targets.
- `environmental_match` differs between the `spatial_weights` run and a
  version with `spatial_weights` removed (falls back to
  `environmental_triggers`) for all 297 trees, max difference 0.59 --
  confirms `land_cover` is genuinely engaging, not silently falling
  back to the old moisture/temp path.
- `risk_score` range with `spatial_weights`: 0.000-0.701. Without
  (fallback): 0.000-0.746. Both nonzero and in a sane 0-1 range; the
  difference is expected since the two paths compute environmental
  match completely differently.

### Regression -- PASS
Re-ran `run_real_site_risk_raster.py`, `run_real_site_tree_risk.py`,
`run_real_site_tree_spread.py` after the `pathogens.py` change. All
three real-site pathogens produced identical numbers to the values
already recorded in `docs/feature_contracts/temporal_spread_per_tree.md`
and `docs/feature_contracts/site_tree_host_inventory.md`: raster risk
ranges 0.000-0.405 / 0.000-0.079 / 0.000-0.229; `anthracnose` spread
still 6 generations / 27 trees; `phytophthora` spread still stalls at
generation 1 with 0 trees. The `emerald_ash_borer` config addition
changed nothing for the other three pathogens.

### Not verified (see Non-goals)
`wetness`'s contribution is not exercised in the run above --
`generate_synthetic_spatial_surfaces` has no `wetness` key, so it is
silently dropped and `land_cover` alone determines
`environmental_match`, renormalized to weight 1.0. Confirmed only once
a real EAB site (with `load_site_grid`'s `wetness` surface) exists.
