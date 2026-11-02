# Feature contract: Real wind data via nearest-station lookup

## Status
This contract unblocks Part B of `docs/feature_contracts/wind_dispersal_and_soil_reweight.md`
("directional dispersal kernel"). Part B was parked. It needed a real
wind data source, because "no wind direction/frequency data exists in the `.gdb` or
anywhere else in the project."

This contract covers how to get and derive that data for each site.
It does **not** cover the dispersal-kernel change. That change uses this data.
It stays a separate follow-on contract after this one is done.

## Problem
`red_ring_rot` (and any future airborne or vector pathogen) has no real
prevailing-wind information. The isotropic dispersal kernel in
`spread_engine.py` treats every direction from a known case as equally
likely. This understates risk downwind and overstates it upwind. The gap
is known and documented. It was not actionable until now.

## Goal
For each site AOI, find the nearest real weather station with a usable
historical wind record. From that station, derive a prevailing direction
and a directionality strength. A future kernel change then uses real data,
not a placeholder.

## Data source
Iowa Environmental Mesonet (IEM). It is hosted by the Department of
Agronomy at Iowa State University. IEM is public and needs no login. It
serves NOAA's ASOS/AWOS station network. The network is nationwide, not
Iowa-only.

IEM was chosen over NOAA's Climate Data Online API. CDO requires a signup
and a token step. IEM does not.

Two endpoints. Both were confirmed working during this contract's research:

- Station list: `https://mesonet.agron.iastate.edu/geojson/network.py?network=OR_ASOS`
  (GeoJSON). One feature per Oregon ASOS/AWOS station, with `sid` (station id) and lat/lon.
- Wind rose data: `https://mesonet.agron.iastate.edu/cgi-bin/mywindrose.py?station=<SID>&network=OR_ASOS&justdata=true`
  (plain-text CSV-like table). One row per 10-degree direction sector (36
  rows, `355-004` through `345-354`). Columns hold calm % and 6 wind-speed
  bins (mph) as percent frequency. The first data row's `Calm` column holds
  the station's overall calm percentage. This is a station-wide value. It is
  not specific to that row's direction sector. Every other row leaves that
  column blank. Both endpoints are reachable from the plain `.venv` with
  stdlib `urllib.request`. No new dependency is needed, and arcpy is not
  needed. This is the first project data source that is not a GIS file or service.

Nearest stations found for the current sites. Distance is haversine,
from each AOI centroid. The centroid is computed with arcpy `projectAs` to WGS84.
`RedRingRot` -> `77S` (Creswell Hobby Field, 9.8 km, 58,043 obs since 2019);
`Phytophthora` -> `EUG` (Eugene/Mahlon Sweet, 9.1 km, 597,201 obs since
1948). Both stations are close enough to be reasonably representative. Both
have large records. This is not true of every Oregon ASOS/AWOS station.
Some have sparse records or are offline.

## Scope
- A new per-site step: `PathogenPy/fetch_wind_rose.py`. It runs in the plain
  `.venv`, not arcpy. It runs after `export_site_layers.py`. It needs only
  each site's AOI centroid (already in `grid_meta.json`) and network access.
  1. Reproject the AOI centroid to lat/lon. Do this once, in
     `export_site_layers.py`, where arcpy is available. Store
     `centroid_lat`/`centroid_lon` in `grid_meta.json`. Do not repeat the
     projection in the plain venv. That venv has no pyproj or arcpy.
  2. Fetch the `OR_ASOS` station list. Find the nearest station by
     haversine distance to the centroid.
  3. Fetch that station's wind rose `justdata` table. Parse it into
     per-sector frequencies.
  4. Derive `prevailing_direction_deg` and `directionality_strength` with
     circular statistics (see the design note). Do not just pick the
     largest sector. That method is noisier. It also ignores the rest of the distribution.
  5. Write `data/<site>/wind_rose.json`. It holds the station id, name, and
     distance. It holds the two derived values. It also holds the raw
     parsed sector table. The raw table supports provenance and later
     re-derivation. It is not only for the two headline numbers.
- A station with no data or sparse data triggers a fallback. The script
  uses the next-nearest station. A station in the network list does not
  guarantee a usable wind record. Confirm that data exists. Do not assume it.

## Non-goals
- No change to `spread_engine.py`'s dispersal kernel. No change to
  `pathogens.py`'s `spatial_weights` or config in this pass. `wind_rose.json`
  is produced but not yet used by the risk model. That is the kernel change
  in Part B. It is a separate follow-on contract, after this data exists.
- No coverage of sites outside Oregon. The `OR_ASOS` network scope matches
  the project's current data. All sites are Oregon AOIs. A non-Oregon site
  needs a different network code. This contract does not handle that.
- No caching or refresh strategy. The data is written to `data/<site>/` once.
  This matches every other exported site input. To update it, re-run the script.
- No claim that one nearest station's long-term climate is a perfect match
  for the AOI's wind exposure. Local terrain channels wind at scales finer
  than a 9-19 km station offset can capture. The source is real and
  reasonably representative. It is not validated for this specific site.

## Inputs
- `data/<site>/grid_meta.json` (gains `centroid_lat`/`centroid_lon`).
- IEM's public `OR_ASOS` network and wind rose endpoints (see Data source).

## Outputs
- `grid_meta.json` gains `centroid_lat`/`centroid_lon` for both sites.
- `data/<site>/wind_rose.json`: `station_id`, `station_name`,
  `distance_km`, `prevailing_direction_deg`, `directionality_strength`,
  `sector_frequencies` (raw parsed table).

## Success criteria
- Both sites produce a `wind_rose.json`. The station is within a reasonable
  distance. This is documented, not enforced by a hard threshold. The
  station has a non-trivial historical observation count.
- `prevailing_direction_deg` and `directionality_strength` are sane and
  explainable on inspection. For example, check them against the station's
  known regional wind pattern. A number alone is not enough.
- The script runs cleanly on both sites. It has no network or parsing
  errors. It uses only the plain `.venv`. This confirms that the arcpy and
  non-arcpy split still holds for this new data source.

## Definition of done
- This contract exists (done).
- The design note, implementation, verification, and update summary follow
  in `docs/notes/real_wind_data.md`.
