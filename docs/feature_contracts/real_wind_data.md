# Feature contract: Real wind data via nearest-station lookup

## Status
Unblocks Part B of `docs/feature_contracts/wind_dispersal_and_soil_reweight.md`
("directional dispersal kernel"), which was explicitly parked pending a real
wind data source ("no wind direction/frequency data exists in the `.gdb` or
anywhere else in the project"). This contract covers acquiring and deriving
that data per site -- **not** the dispersal-kernel change that will consume
it, which stays a separate follow-on contract once this lands.

## Problem
`red_ring_rot` (and any future airborne/vector pathogen) has no real
prevailing-wind information. The isotropic dispersal kernel in
`spread_engine.py` treats every direction from a known case as equally
likely, which understates risk downwind and overstates it upwind -- a
known, previously-documented gap, just never actionable before now.

## Goal
For each site AOI, look up the nearest real weather station with a usable
historical wind record and derive a prevailing direction and a
directionality strength from it, so a future kernel change has real data
to consume instead of a placeholder.

## Data source
Iowa Environmental Mesonet (IEM), hosted by Iowa State University's
Department of Agronomy -- a public, unauthenticated reflector for NOAA's
ASOS/AWOS station network (nationwide, not Iowa-specific; chosen over
NOAA's own Climate Data Online API specifically because CDO requires a
signup/token step and IEM doesn't). Two endpoints, both confirmed working
during this contract's research:

- Station list: `https://mesonet.agron.iastate.edu/geojson/network.py?network=OR_ASOS`
  -- GeoJSON, one feature per Oregon ASOS/AWOS station, with `sid`
  (station id) and lat/lon.
- Wind rose data: `https://mesonet.agron.iastate.edu/cgi-bin/mywindrose.py?station=<SID>&network=OR_ASOS&justdata=true`
  -- plain-text CSV-like table, one row per 10-degree direction sector (36
  rows, `355-004` through `345-354`), columns for calm % and 6 wind-speed
  bins (mph) as percent-frequency. The first data row's `Calm` column
  holds the station's overall calm percentage (a station-wide scalar, not
  specific to that row's direction sector) -- everywhere else that column
  is blank. Both endpoints confirmed reachable from the plain `.venv` via
  stdlib `urllib.request` -- no new dependency, no arcpy needed (this is
  the first project data source that isn't a GIS file/service).

Nearest stations found for the current sites (haversine distance from each
AOI centroid, centroid computed via arcpy `projectAs` to WGS84):
`RedRingRot` -> `77S` (Creswell Hobby Field, 9.8 km, 58,043 obs since 2019);
`Phytophthora` -> `EUG` (Eugene/Mahlon Sweet, 9.1 km, 597,201 obs since
1948). Both close enough to be reasonably representative and have
substantial records -- not a given for every Oregon ASOS/AWOS station,
some of which are sparse or offline.

## Scope
- A new per-site step, `PathogenPy/fetch_wind_rose.py`, run in the plain
  `.venv` (not arcpy) after `export_site_layers.py`, since it only needs
  each site's AOI centroid (already in `grid_meta.json`) plus network
  access:
  1. Reproject the AOI centroid to lat/lon -- done once, in
     `export_site_layers.py` (arcpy already available there), storing
     `centroid_lat`/`centroid_lon` in `grid_meta.json` rather than
     re-deriving the projection in the plain venv (which has no
     pyproj/arcpy).
  2. Fetch the `OR_ASOS` station list, compute the nearest station by
     haversine distance to the centroid.
  3. Fetch that station's wind rose `justdata` table, parse into
     per-sector frequencies.
  4. Derive `prevailing_direction_deg` and `directionality_strength` via
     circular statistics (see design note) over the sector frequencies --
     not just "pick the max sector," which would be noisier and ignore
     the rest of the distribution.
  5. Write `data/<site>/wind_rose.json`: station id/name/distance, the two
     derived values, and the raw parsed sector table (for provenance/
     future re-derivation, not just the two headline numbers).
- Handles a station with no/sparse data by falling back to the
  next-nearest station (a station existing in the network list doesn't
  guarantee it has a usable wind record -- confirm data presence, don't
  assume).

## Non-goals
- No change to `spread_engine.py`'s dispersal kernel or to
  `pathogens.py`'s `spatial_weights`/config in this pass -- `wind_rose.json`
  is produced but not yet consumed by the risk model. That's Part B's
  kernel change, a distinct follow-on contract once this data exists.
- No attempt to cover sites outside Oregon -- the `OR_ASOS` network scope
  matches the project's current data (all sites are Oregon AOIs). A
  non-Oregon site would need a different network code, not handled here.
- No caching/refresh strategy for the fetched data beyond writing it to
  `data/<site>/` once -- same treatment as every other exported site
  input, re-run the script if it needs updating.
- No claim that a single nearest station's long-term climatology is a
  perfect stand-in for the AOI's actual wind exposure (local terrain
  channels wind at scales finer than a 9-19 km station offset can
  capture) -- a real, but reasonably representative, data source; not
  validated for this specific site.

## Inputs
- `data/<site>/grid_meta.json` (gains `centroid_lat`/`centroid_lon`).
- IEM's public `OR_ASOS` network + wind rose endpoints (see Data source).

## Outputs
- `grid_meta.json` gains `centroid_lat`/`centroid_lon` for both sites.
- `data/<site>/wind_rose.json`: `station_id`, `station_name`,
  `distance_km`, `prevailing_direction_deg`, `directionality_strength`,
  `sector_frequencies` (raw parsed table).

## Success criteria
- Both sites produce a `wind_rose.json` with a station within a
  reasonable distance (documented, not enforced by a hard threshold) and
  a non-trivial historical observation count.
- `prevailing_direction_deg`/`directionality_strength` are sane and
  explainable on inspection (e.g., cross-checked against the station's
  known regional wind pattern, not just "a number came out").
- Script runs cleanly against both sites with no network/parsing errors,
  using only the plain `.venv` (confirms the arcpy/non-arcpy split still
  holds for this new data source).

## Definition of done
- This contract exists (done).
- Design note, implementation, verification, and update summary follow in
  `docs/notes/real_wind_data.md`.
