# Feature contract: Richer soil water attributes for phytophthora suitability

## Problem
The current soil suitability surface (`spatial_inputs.DRAINAGE_CLASS_SCORES`)
is a single ordinal ramp over `muaggatt.drclassdcd`'s 7 dominant-drainage
classes, with the 7 numeric scores chosen by domain judgment, not measured
data. It's the only soil signal feeding phytophthora's `spatial_weights`
(currently weighted 0.55, the largest single weight of any surface for any
pathogen -- see `pathogens.py`), so its placeholder-ness carries a lot of
the model's real weight.

`gNATSGO_OR.gdb/muaggatt` (already joined once for `drclassdcd`) carries
several more directly water-relevant fields that aren't being used:
`hydgrpdcd` (hydrologic soil group, A-D, a standard runoff/infiltration
rating), `wtdepannmin` (annual minimum water table depth, inches),
`wtdepaprjunmin` (April-June minimum water table depth -- the wet-season
window relevant to zoospore activity), `flodfreqdcd`/`pondfreqprs` (flood/
ponding frequency), and `drclasswettest` (wettest drainage class within the
map unit, vs. just the dominant one).

Confirmed via a one-off diagnostic query before committing to this: both
site AOIs (`RedRingRot`, `Phytophthora`) span 17 distinct map units each,
with real variation in `hydgrpdcd` (Phytophthora's AOI spans A through D)
and `wtdepannmin` (0-46in at RedRingRot, up to 76in at Phytophthora, mixed
with many `None`/not-applicable cells on well-drained units). This isn't a
degenerate case where the AOI is one uniform soil unit -- there's real
signal to add.

## Goal
Replace the single-field ordinal soil score with a combination of several
real gNATSGO water/drainage attributes, so the soil suitability surface
rests on more than one guessed ramp, without pretending the result is a
validated model -- it's still domain-judgment combination logic, just of
real inputs instead of one.

## Scope
- Export two additional soil surfaces from `gNATSGO_OR.gdb/muaggatt`
  alongside the existing `drclassdcd`-derived one, joined in the same pass:
  - `hydgrpdcd` -> a small ordinal code (A-D; dual ratings like `"A/D"`
    resolve to the second/undrained letter per NRCS convention, since that
    reflects natural, undrained site conditions).
  - `wtdepannmin` -> passed through numerically (inches). `NULL` (no water
    table within the reported depth) is filled with a sentinel that reads
    as "deep/dry" after normalization, not silently treated as 0 (which
    would mean "water table at the surface" -- the opposite meaning).
- Combine `soil_drainage` (existing), the new hydrologic-group score, and
  the new water-table-depth score into one `soil` suitability surface via
  a simple unweighted average -- explainable, no new tunable weights
  introduced in this pass.
- Re-run the full pipeline (export -> compute -> import) for both sites and
  confirm the resulting rasters still make sense.

## Non-goals
- `wtdepaprjunmin`, `flodfreqdcd`, `pondfreqprs`, `drclasswettest`,
  `aws0100wta` are documented candidates for a future pass, not included
  here -- keeping this round to two additions so the combination logic
  stays inspectable.
- No claim that the combined score is validated -- same caveat as the
  drainage-class score it's extending, now spread across three real inputs
  instead of one.
- Terrain/topographic-wetness-index rework (the other half of the earlier
  discussion) is out of scope for this contract -- tracked separately.
- Doesn't touch `red_ring_rot` -- it currently has no `soil` weight
  (dropped per `docs/feature_contracts/wind_dispersal_and_soil_reweight.md`)
  and this doesn't reintroduce one.

## Inputs
- `gNATSGO_OR.gdb/muaggatt`: `hydgrpdcd`, `wtdepannmin` (in addition to the
  already-used `drclassdcd`).
- `gNATSGO_OR.gdb/MapunitRaster_10m`: unchanged, already the join target.

## Outputs
- `data/<site>/hydro_group_code.npy` + `data/<site>/hydro_groups.json`
  (code->label crosswalk), `data/<site>/water_table_depth_in.npy`.
- `spatial_inputs.load_site_grid`'s `soil` surface now reflects all three
  inputs instead of one.
- Updated `outputs/*_site_risk.npy`/`.tif`/preview for both sites.

## Success criteria
- Both sites' exports run end to end with the two new fields joined and no
  `ValueError`/shape mismatch.
- The combined `soil` surface visibly differs from the old
  `drclassdcd`-only surface somewhere in each AOI (i.e. the new fields
  aren't just duplicating the old signal) -- checked by comparing the two
  surfaces directly, not just eyeballing the final risk raster.
- `run_real_site_risk_raster.py` and `import_risk_raster.py` still run
  cleanly for both pathogens.

## Definition of done
- This contract exists (done).
- Design note, implementation, verification, and update summary follow in
  `docs/notes/soil_water_attributes.md`.
