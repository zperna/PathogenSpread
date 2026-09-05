# Design note: Real wind data via nearest-station lookup

## Approach

### Centroid lat/lon (arcpy side)
`export_site_layers.py`'s `export_case_layer` already computes
`aoi_extent` in `TARGET_SR` (UTM 10N, meters). Add one `projectAs` call to
WGS84 (arcpy already does this exact kind of reprojection elsewhere, e.g.
the DEM service's AOI-corner reprojection) on the AOI centroid, and store
`centroid_lat`/`centroid_lon` in the existing `grid_meta.json`. This keeps
all coordinate-system math confined to the arcpy-only script, consistent
with the project's existing split -- the plain-venv wind-rose script never
needs to touch a projection.

### Nearest-station lookup (plain venv, `fetch_wind_rose.py`)
1. Fetch `https://mesonet.agron.iastate.edu/geojson/network.py?network=OR_ASOS`
   via `urllib.request` (stdlib, no new dependency), parse the GeoJSON
   `features` list for each station's `sid` and lat/lon.
2. Haversine distance from the site centroid to every station; sort
   ascending.
3. Walk the sorted list nearest-first, fetching
   `https://mesonet.agron.iastate.edu/cgi-bin/mywindrose.py?station=<sid>&network=OR_ASOS&justdata=true`
   for each candidate until one returns a parseable table with a
   non-trivial observation count (the comment header's
   `Observations Used/Missing/Total` line) -- don't assume the nearest
   station in the network list necessarily has a usable record.

### Parsing the wind rose table
The response is a commented CSV: lines starting `#` are metadata (including
the total observation count, useful to sanity-check data volume), then a
header row and 36 data rows, one per 10-degree direction sector (e.g.
`355-004`, `005-014`, ... `345-354`). Columns are `Direction, Calm,
2.0-4.9, 5.0-6.9, 7.0-9.9, 10.0-14.9, 15.0-19.9, 20.0+` (percent
frequency, mph bins). Only the *first* data row's `Calm` cell is
populated -- it holds the station's overall calm percentage as a
station-wide scalar, not a value for that row's direction sector
specifically (an IEM table-layout quirk, confirmed by fetching the raw
text directly rather than trusting a summarized description of it). Parse
that separately from the per-sector totals.

For each direction sector, sum the six speed-bin percentages (excluding
`Calm`) to get that sector's total frequency. Sector center degree =
`int(first three digits of the label) + 5, mod 360` (e.g. `175-184` ->
180; `355-004` -> 0).

### Deriving prevailing direction and directionality strength
Standard circular-statistics treatment, not just "pick the max sector"
(which throws away the shape of the rest of the distribution and is
noisier sector-to-sector):

```
sin_sum = sum(freq_i * sin(radians(center_deg_i)) for each sector i)
cos_sum = sum(freq_i * cos(radians(center_deg_i)) for each sector i)
total_freq = sum(freq_i for each sector i)   # excludes calm

prevailing_direction_deg = degrees(atan2(sin_sum, cos_sum)) % 360
directionality_strength = sqrt(sin_sum**2 + cos_sum**2) / total_freq
```

This is the mean resultant direction/length of a circular distribution:
`directionality_strength` is bounded 0-1 -- 0 if wind is equally likely
from every direction (vectors cancel out), approaching 1 if it's
overwhelmingly from one direction (vectors reinforce). Calm observations
are excluded from both sums (a calm reading has no direction to
contribute), so `directionality_strength` describes the directionality of
the wind *when it's blowing*, not conflated with how often it's calm.

## Output shape
`data/<site>/wind_rose.json`:
```json
{
  "station_id": "EUG",
  "station_name": "EUGENE/MAHLON SWEET",
  "distance_km": 9.1,
  "observation_count": 597201,
  "calm_percent": 13.13,
  "prevailing_direction_deg": 176.4,
  "directionality_strength": 0.34,
  "sector_frequencies": {"355-004": 8.196, "005-014": 3.835, ...}
}
```
`sector_frequencies` (per-sector total, calm excluded) is kept for
provenance/debugging and so a future kernel change (or a person
double-checking this) doesn't have to re-fetch and re-parse the raw table
to see what the two headline numbers were derived from.

## Assumptions
- Nearest-station-by-straight-line-distance is the selection rule, not
  e.g. "most similar elevation/terrain" -- simplest defensible choice,
  consistent with the contract's non-goal of not claiming perfect
  representativeness.
- No hard distance cutoff enforced (a station 9-19 km away is used as-is)
  -- the contract requires this be documented and sanity-checked per site,
  not silently accepted past some threshold. Both current sites landed
  under 10 km, which is comfortably close for this purpose.
- Mean resultant length was chosen over other possible directionality
  measures (e.g., ratio of max sector to mean sector) because it's a
  standard, well-understood circular-statistics quantity that uses the
  whole distribution rather than a single sector, making it less sensitive
  to noise in any one 10-degree bin.

## Verification
Full run for both sites (2026-09-04):

1. Added `centroid_lat`/`centroid_lon` to `export_site_layers.py`, re-ran
   under Pro's Python -- both sites' `grid_meta.json` gained the fields,
   matching an independent manual `arcpy.PointGeometry.projectAs` check
   done earlier in this session (same values to full precision).
2. `fetch_wind_rose.py` (plain `.venv`) -- first run hit a real issue, not
   a bug: `EUG`'s `justdata=true` query (597k observations since 1948)
   took ~47s server-side (confirmed by direct `curl` timing), longer than
   the initial 30s timeout, so all 3 retries against `EUG` timed out and
   the script correctly fell back to the next-nearest station (`77S`,
   19.3 km, worse than `EUG`'s 9.1 km). Raised the timeout to 120s instead
   of accepting the worse fallback; re-run got `EUG` directly.
3. Final results, both sane and sector totals + calm summing to ~100%
   (99.99% / 100.01%, rounding):
   - `RedRingRot` site -> `77S` (Creswell Hobby Field), 9.8 km, 58,044 obs
     (since 2019), 54.77% calm, prevailing 270.7 deg (west),
     directionality strength 0.428.
   - `Phytophthora` site -> `EUG` (Eugene/Mahlon Sweet), 9.1 km, 597,202
     obs (since 1948), 13.13% calm, prevailing 224.7 deg (southwest),
     directionality strength 0.156.
   `77S`'s high calm percentage is plausible for a small unstaffed
   airfield (anemometer siting/threshold effects commonly overreport calm
   at these stations relative to a major airport like `EUG`) -- noted as
   context, not treated as a data-quality problem requiring a fallback.
4. **Caveat worth flagging for whoever builds the Part B kernel next**:
   the Willamette Valley (where both sites sit) has a well-known
   terrain-channeled, often bimodal seasonal wind pattern (e.g. more
   southerly in winter storms, more northerly in summer). A single
   all-season circular mean partially cancels opposing seasonal modes
   against each other, which is a likely contributor to `EUG`'s
   comparatively low directionality strength (0.156) -- not necessarily
   "this station has weak wind directionality" so much as "the summer and
   winter prevailing directions partially cancel in an annual average."
   This wasn't corrected here (out of scope -- this contract derives a
   single-mean data point, not a seasonal model), but it's the first thing
   to reconsider if the eventual kernel change wants a more seasonally-
   aware wind bias.

## Update summary
- Contract, design note, `export_site_layers.py` centroid lat/lon, and
  `fetch_wind_rose.py` (station lookup, wind rose fetch/parse, circular-
  statistics derivation, retry/timeout handling, sparse-station fallback):
  all done this session.
- Real bug caught and fixed during verification (not shipped silently):
  the initial 30s fetch timeout was too short for a large-history station
  (`EUG`), which would have silently downgraded both sites to the same,
  farther fallback station rather than each getting its true nearest one.
  Caught by noticing the fallback distance (19.3 km) was worse than
  expected, not by an exception -- worth remembering that "the script
  didn't crash" isn't the same as "it got the right answer."
- `data/site/wind_rose.json` and `data/site_phytophthora/wind_rose.json`
  now exist with real station data. Nothing in `pathogens.py` or
  `spread_engine.py` consumes them yet -- that's the explicitly separate
  Part B follow-on.
- Remaining for next iteration: the directional/anisotropic dispersal
  kernel change itself (Part B of `wind_dispersal_and_soil_reweight.md`),
  now unblocked by this data. Whoever picks that up next should read the
  seasonal-bimodality caveat above before treating `directionality_strength`
  as a simple confidence dial.