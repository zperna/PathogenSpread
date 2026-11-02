# Feature contract: Richer soil water attributes for phytophthora suitability

## Problem
The current soil suitability surface (`spatial_inputs.DRAINAGE_CLASS_SCORES`) is a single ordinal ramp. It covers the 7 dominant-drainage classes in `muaggatt.drclassdcd`. Domain judgment chose the 7 numeric scores. They are not measured data.

This surface is the only soil signal that feeds phytophthora's `spatial_weights`. Its weight is 0.55. That is the largest single weight of any surface for any pathogen (see `pathogens.py`). So its placeholder status carries much of the model's real weight.

`gNATSGO_OR.gdb/muaggatt` was already joined once, for `drclassdcd`. It holds several more water-relevant fields that are not used yet:
- `hydgrpdcd`: hydrologic soil group, A-D. A standard runoff and infiltration rating.
- `wtdepannmin`: annual minimum water table depth, in inches.
- `wtdepaprjunmin`: April-June minimum water table depth. This is the wet-season window relevant to zoospore activity.
- `flodfreqdcd` and `pondfreqprs`: flood and ponding frequency.
- `drclasswettest`: the wettest drainage class within the map unit, not just the dominant one.

This was confirmed with a one-off diagnostic query before the work was committed. Both site AOIs (`RedRingRot`, `Phytophthora`) span 17 distinct map units each. The data varies in two fields:
- `hydgrpdcd`: Phytophthora's AOI spans A through D.
- `wtdepannmin`: 0-46in at RedRingRot, up to 76in at Phytophthora. Many cells on well-drained units are `None` (not applicable).

This is not a degenerate case where the AOI is one uniform soil unit. There is real signal to add.

## Goal
Replace the single-field ordinal soil score with a combination of several real gNATSGO water and drainage attributes. The soil suitability surface then rests on more than one guessed ramp.

The result is not presented as validated. It is still domain-judgment combination logic. The difference is that it uses several real inputs, not one.

## Scope
- Export two more soil surfaces from `gNATSGO_OR.gdb/muaggatt`. Join them in the same pass as the existing `drclassdcd` surface.
  - `hydgrpdcd` becomes a small ordinal code (A-D). Dual ratings such as `"A/D"` resolve to the second, undrained letter. This follows NRCS convention, because it reflects natural, undrained site conditions.
  - `wtdepannmin` is passed through as numbers (inches). `NULL` means no water table within the reported depth. It is filled with a sentinel that reads as "deep/dry" after normalization. It is not treated as 0. A value of 0 would mean "water table at the surface," which is the opposite meaning.
- Combine three inputs into one `soil` suitability surface: `soil_drainage` (existing), the new hydrologic-group score, and the new water-table-depth score. Use a simple unweighted average. This is explainable. This pass adds no new tunable weights.
- Re-run the full pipeline (export, compute, import) for both sites. Confirm that the rasters still make sense.

## Non-goals
- `wtdepaprjunmin`, `flodfreqdcd`, `pondfreqprs`, `drclasswettest`, and `aws0100wta` are documented candidates for a future pass. They are not part of this round. This round keeps to two additions so the combination logic stays inspectable.
- No claim is made that the combined score is validated. It carries the same caveat as the drainage-class score it extends. The caveat now spans three real inputs, not one.
- The terrain and topographic wetness index rework (the other half of the earlier discussion) is out of scope. It is tracked separately.
- This does not touch `red_ring_rot`. It has no `soil` weight at present. The weight was dropped per `docs/feature_contracts/wind_dispersal_and_soil_reweight.md`. This change does not add one back.

## Inputs
- `gNATSGO_OR.gdb/muaggatt`: `hydgrpdcd` and `wtdepannmin`, in addition to the already-used `drclassdcd`.
- `gNATSGO_OR.gdb/MapunitRaster_10m`: unchanged. It remains the join target.

## Outputs
- `data/<site>/hydro_group_code.npy`, `data/<site>/hydro_groups.json` (code-to-label crosswalk), and `data/<site>/water_table_depth_in.npy`.
- The `soil` surface returned by `spatial_inputs.load_site_grid` now reflects all three inputs, not one.
- Updated `outputs/*_site_risk.npy`, `.tif`, and preview files for both sites.

## Success criteria
- Both sites' exports run end to end with the two new fields joined. There is no `ValueError` and no shape mismatch.
- The combined `soil` surface visibly differs from the old `drclassdcd`-only surface somewhere in each AOI. In other words, the new fields do not just repeat the old signal. Check this by comparing the two surfaces directly. Do not rely on eyeballing the final risk raster.
- `run_real_site_risk_raster.py` and `import_risk_raster.py` still run cleanly for both pathogens.

## Definition of done
- This contract exists (done).
- The design note, implementation, verification, and update summary follow in `docs/notes/soil_water_attributes.md`.
