# Feature contract: emerald ash borer spatial_weights (config only)

## Status
This is config only. The user chose this scope. No real EAB case exists yet,
so this contract does not build a real site. It closes the config gap. Then a real
site can be wired in later, the same way `anthracnose` was
(`docs/feature_contracts/anthracnose_site_risk.md`). That happens when a confirmed case exists.

## Problem
`emerald_ash_borer` is the only pathogen in `pathogens.py` with no
`spatial_weights` block. `compute_risk_raster` needs at least one
`spatial_weights` surface in the environment to set the raster's shape. So it
cannot run for this pathogen today, on a real site or a synthetic one.

`compute_risk` falls back to the `environmental_triggers` moisture and
temperature path when `spatial_weights` is absent. That fallback works with
`synthetic_data.generate_environment_grid`. It would raise a `KeyError` with
`spatial_inputs.load_site_grid` (real sites), because that function has no
`moisture` or `temp` keys. The same caveat is recorded in
`docs/notes/site_tree_host_inventory.md`'s Assumptions.

The POS integration makes this worth doing now, even without a real case.
`Fraxinus` (ash) is well represented at every existing site. The counts are
`site` 214, `site_phytophthora` 152, and `site_anthracnose` 173 trees. These are
oregon_ash and green_ash combined. See
`docs/feature_contracts/site_tree_host_inventory.md`'s Verification.

## Goal
Give `emerald_ash_borer` a `spatial_weights` block. Reason it through the
pathogen's own transmission biology, not copied from another pathogen. Then it
is ready to run as soon as a real case exists. Verify what can be checked
without one. Check that the math runs, and that the new surfaces change the
result. Use synthetic data for this.

## Scope
1. **`pathogens.py`: add `emerald_ash_borer["spatial_weights"]`.**
   EAB spreads by flight. Adult beetles fly to find ash. Larvae bore under the bark.
   It is not spread by wind or rain, and it is not root contact. It is a third
   mechanism. No other pathogen with a `spatial_weights` block uses it.
   - `land_cover` (0.7): the beetle still needs a real tree canopy to land in
     and colonize at the site it reaches. This is the same host and canopy
     density role that `land_cover` plays for the other three pathogens.
   - `wetness` (0.3), the DEM-derived topographic wetness index (see
     `docs/feature_contracts/topographic_wetness_index.md`). It is a
     **host-habitat proxy**, not a moisture-triggers-infection mechanism. Oregon
     ash (`Fraxinus latifolia`) is typically a wetland or riparian species in the
     Willamette Valley. So higher TWI is a proxy for "more likely ash habitat."
     This is a different causal claim from `phytophthora`'s use of the same
     surface, where root-zone moisture triggers infection. Reusing `wetness`
     here is not the mistake that `wind_dispersal_and_soil_reweight.md` warned
     about, which is copying a surface without reasoning it through. This is
     the same surface doing a different, stated job.
   - `exposure`, `terrain`, and `soil` are left out on purpose. There is no
     wind-exposure wound infection route, as in `red_ring_rot`. There is no root contact, as in `phytophthora`.
   - `environmental_triggers` (`temp_weight` and `moisture_weight`) stays in the
     config. It is superseded for the real-site path once `spatial_weights` is
     set. Other pathogens follow the same pattern. It is not authoritative, but it is kept. A comment
     records this, in the same style as `red_ring_rot`'s existing comment.
2. **No other file changes.** No `export_site_layers.py` `CASE_LAYERS` entry. No
   `RUNS` entry in `run_real_site_risk_raster.py`, `run_real_site_tree_risk.py`,
   or `run_real_site_tree_spread.py`. No `data/site_eab/`. All of these are
   deferred to a follow-on contract, for when a real case exists.

## Inputs
- The existing `emerald_ash_borer` config in `pathogens.py`. Transmission mode,
  dispersal constants, host susceptibility, and stress multiplier are all unchanged.
- Synthetic data only, for verification:
  `synthetic_data.generate_inventory` (the species pool includes `oregon_ash`
  and `green_ash`) and `spatial_inputs.generate_synthetic_spatial_surfaces`
  (it has `land_cover` and no `wetness`. See Non-goals).

## Outputs
- Updated `pathogens.py`.
- This contract. The verification is recorded here or in a design note.

## Success criteria
1. `compute_risk` runs for `emerald_ash_borer` against a synthetic inventory and
   `generate_synthetic_spatial_surfaces` with no error.
2. The `environmental_match` column differs visibly from a run with
   `spatial_weights` removed. This confirms that `land_cover` takes part. It
   also confirms that the code is not silently falling back.
3. The other three pathogens are unchanged. This is the regression check.
   `run_real_site_risk_raster.py`, `run_real_site_tree_risk.py`, and
   `run_real_site_tree_spread.py` all produce output that diffs clean.
4. The reasoning for `land_cover` and `wetness` is written down separately from
   `anthracnose`'s use of the same two surfaces. A future reader should not
   mistake this for a copy-paste.

## Non-goals
1. **No real site.** There is no known-case feature class, no `data/site_eab/`,
   and no raster or per-tree run on real data. The "config only" choice exists for this reason. Real runs are deferred to a follow-on contract.
2. **`wetness`'s contribution is not verified end to end.**
   `generate_synthetic_spatial_surfaces` has no `wetness` key. So in the
   synthetic verification run, `_combine_spatial_environment` silently drops
   `wetness` (`if surface_name not in environment: continue`). It then
   renormalizes the weights. Only `land_cover` is actually used. The `wetness`
   part of this reasoning is confirmed only once a real EAB site exists. That
   site's `load_site_grid` output does include `wetness`. Recorded here. Not worked around with a synthetic surface, which would be another placeholder.
3. **`max_dispersal_distance_m` (3,000 m) is larger than the current AOI.** Every
   existing site is a 2 km square (`AOI_HALF_SIZE_M = 1000` in
   `export_site_layers.py`). If a real EAB site is built the same way, the
   dispersal kernel would almost never reach its cap inside the AOI. This is flagged for whoever writes that follow-on contract. It is not addressed here.
4. No validation against real EAB pathology literature. The weights are
   domain judgment, with the same caveat as every other pathogen's `spatial_weights`.

## Definition of done
1. This contract exists (done).
2. No separate design note. The reasoning is fully recorded in the Scope above.
   The verification is recorded directly here. This is proportionate to a config-only change.
3. `pathogens.py` is updated (done).
4. The synthetic verification run is recorded (done, 2026-09-11).
5. Regression on the three real-site pathogens is confirmed clean (done, 2026-09-11).

## Verification (2026-09-11)

### Synthetic run: PASS
`compute_risk` ran against `synthetic_data.generate_inventory(area_size_m=1200, n_trees=300)`.
The species pool includes `oregon_ash` and `green_ash`. The seeded run has 64 ash
trees. It also ran against `spatial_inputs.generate_synthetic_spatial_surfaces(area_size_m=1200)`.
That function has `land_cover` and no `wetness`. See Non-goals.
- It ran without error for all 297 non-infected targets.
- `environmental_match` differs between the `spatial_weights` run and a version
  with `spatial_weights` removed. That version falls back to `environmental_triggers`.
  The difference holds for all 297 trees. The maximum difference is 0.59. This
  confirms that `land_cover` is genuinely engaged. The code is not silently falling back to the old moisture and temperature path.
- The `risk_score` range with `spatial_weights` is 0.000-0.701. Without it (the
  fallback) it is 0.000-0.746. Both are nonzero and within a sane 0-1 range. The
  difference is expected, because the two paths compute the environmental match in completely different ways.

### Regression: PASS
`run_real_site_risk_raster.py`, `run_real_site_tree_risk.py`, and
`run_real_site_tree_spread.py` were re-run after the `pathogens.py` change. All
three real-site pathogens gave the same numbers already recorded in
`docs/feature_contracts/temporal_spread_per_tree.md` and
`docs/feature_contracts/site_tree_host_inventory.md`. The raster risk ranges are
0.000-0.405, 0.000-0.079, and 0.000-0.229. `anthracnose` spread is still 6 generations and 27 trees.
`phytophthora` spread still stalls at generation 1, with 0 trees. The
`emerald_ash_borer` config addition changed nothing for the other three pathogens.

### Not verified (see Non-goals)
`wetness`'s contribution is not exercised in the run above.
`generate_synthetic_spatial_surfaces` has no `wetness` key. So the key is silently
dropped. `land_cover` alone sets `environmental_match`, renormalized to a weight of 1.0. This is only confirmed once a real EAB site exists, with `load_site_grid`'s `wetness` surface.
