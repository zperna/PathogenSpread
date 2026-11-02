# Design note: Real wind data via nearest-station lookup

## Approach

### Centroid lat/lon (arcpy side)
`export_site_layers.py`'s `export_case_layer` already computes
`aoi_extent` in `TARGET_SR` (UTM 10N, meters). Add one `projectAs` call to
WGS84 on the AOI centroid. arcpy already does this kind of reprojection
elsewhere, such as the DEM service's AOI-corner reprojection. Store
`centroid_lat`/`centroid_lon` in the existing `grid_meta.json`. All
coordinate-system math stays in the arcpy-only script. This matches the
project's existing split. The plain-venv wind-rose script never handles a projection.

### Nearest-station lookup (plain venv, `fetch_wind_rose.py`)
1. Fetch `https://mesonet.agron.iastate.edu/geojson/network.py?network=OR_ASOS`
   with `urllib.request` (stdlib, no new dependency). Parse the GeoJSON
   `features` list for each station's `sid` and lat/lon.
2. Compute the haversine distance from the site centroid to every station.
   Sort ascending.
3. Walk the sorted list from nearest to farthest. For each candidate, fetch
   `https://mesonet.agron.iastate.edu/cgi-bin/mywindrose.py?station=<sid>&network=OR_ASOS&justdata=true`.
   Stop at the first station that returns a parseable table with a
   non-trivial observation count. The count is in the comment header's
   `Observations Used/Missing/Total` line. Do not assume the nearest station in the network list has a usable record.

### Parsing the wind rose table
The response is a commented CSV. Lines that start with `#` are metadata.
The total observation count is one of them. It is useful to check data
volume. After the comments come a header row and 36 data rows. Each data row covers one 10-degree direction sector (e.g.
`355-004`, `005-014`, ... `345-354`). Columns are `Direction, Calm,
2.0-4.9, 5.0-6.9, 7.0-9.9, 10.0-14.9, 15.0-19.9, 20.0+` (percent
frequency, mph bins).

Only the *first* data row's `Calm` cell is filled. It holds the station's overall calm percentage. It is a station-wide value. It is not a value for that row's direction sector. This is an IEM table-layout quirk. It was confirmed by fetching the raw text directly, not by trusting a summary of it. Parse this cell separately from the per-sector totals.

For each direction sector, sum the six speed-bin percentages. Do not include `Calm`. The sum is that sector's total frequency. The sector center in degrees is `int(first three digits of the label) + 5, mod 360`. For example, `175-184` gives 180. `355-004` gives 0.

### Deriving prevailing direction and directionality strength
This uses standard circular statistics. It does not just pick the largest sector. That method throws away the shape of the rest of the distribution. It is also noisier from one sector to the next.

```
sin_sum = sum(freq_i * sin(radians(center_deg_i)) for each sector i)
cos_sum = sum(freq_i * cos(radians(center_deg_i)) for each sector i)
total_freq = sum(freq_i for each sector i)   # excludes calm

prevailing_direction_deg = degrees(atan2(sin_sum, cos_sum)) % 360
directionality_strength = sqrt(sin_sum**2 + cos_sum**2) / total_freq
```

This is the mean resultant direction and length of a circular distribution.
`directionality_strength` is bounded from 0 to 1. A value of 0 means the wind is equally likely from every direction, so the vectors cancel out. A value near 1 means the wind comes almost entirely from one direction, so the vectors add up.

Calm observations are excluded from both sums. A calm reading has no direction to add. So `directionality_strength` describes how directional the wind is when it blows. It does not mix in how often the wind is calm.

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
`sector_frequencies` holds the per-sector total, with calm excluded. It is
kept for provenance and debugging. A future kernel change, or a person
checking the results, can see what the two headline numbers came from. They
do not need to fetch and parse the raw table again.

## Assumptions
- The selection rule is the straight-line distance to the nearest station.
  It is not a match on elevation or terrain. This is the simplest defensible
  choice. It fits the contract's non-goal, which says this does not claim
  perfect representativeness.
- No hard distance cutoff is enforced. A station 9-19 km away is used as
  is. The contract requires that the distance be documented and checked for each site. It must not be
  accepted silently past some threshold. Both current sites are under 10 km, which is close enough for this purpose.
- Mean resultant length was chosen over other directionality measures. One
  example is the ratio of the largest sector to the mean sector. Mean
  resultant length is a standard circular-statistics quantity. It uses the
  whole distribution, not one sector. So it is less sensitive to noise in any one 10-degree bin.

## Verification
Full run for both sites (2026-09-04):

1. Added `centroid_lat`/`centroid_lon` to `export_site_layers.py`. Re-ran it
   under Pro's Python. Both sites' `grid_meta.json` gained the fields. The
   values match an independent manual `arcpy.PointGeometry.projectAs` check
   from earlier in this session, to full precision.
2. Ran `fetch_wind_rose.py` in the plain `.venv`. The first run hit a real
   issue. It was not a bug. `EUG`'s `justdata=true` query covers 597k
   observations since 1948. It took about 47 s on the server, which
   direct `curl` timing confirmed. That is longer than the initial 30 s
   timeout. All 3 retries against `EUG` timed out. The script then fell back
   correctly to the next-nearest station, `77S` at 19.3 km. That is farther
   than `EUG`'s 9.1 km. The timeout was raised to 120 s. This was preferred
   over accepting the worse fallback. The re-run got `EUG` directly.
3. Final results. Both are sane. The sector totals plus calm sum to about
   100% (99.99% and 100.01%, from rounding).
   - `RedRingRot` site -> `77S` (Creswell Hobby Field), 9.8 km, 58,044 obs
     (since 2019), 54.77% calm, prevailing 270.7 deg (west),
     directionality strength 0.428.
   - `Phytophthora` site -> `EUG` (Eugene/Mahlon Sweet), 9.1 km, 597,202
     obs (since 1948), 13.13% calm, prevailing 224.7 deg (southwest),
     directionality strength 0.156.
   `77S` has a high calm percentage. That is plausible for a small unstaffed
   airfield. Anemometer siting and threshold effects often overreport calm at
   these stations, compared with a major airport like `EUG`. This is noted as context. It is not treated as a data-quality problem that needs a fallback.
4. **Caveat for whoever builds the Part B kernel next.** The Willamette
   Valley has a known terrain-channeled, often bimodal seasonal wind pattern.
   Winter storms bring more southerly wind. Summer brings more northerly wind.
   A single all-season circular mean partly cancels the opposing seasonal
   modes. This is a likely reason for `EUG`'s low directionality strength of 0.156.
   This does not necessarily mean the station has weak wind directionality. The summer and winter prevailing directions partly cancel in an annual average.
   This was not corrected here. It is out of scope. This contract derives one mean value, not a seasonal model. But it is the first thing to reconsider if the kernel change needs a more seasonally aware wind bias.

## Update summary
- Done this session: the contract, this design note, the centroid lat/lon in
  `export_site_layers.py`, and `fetch_wind_rose.py`. The script covers station
  lookup, wind rose fetch and parse, the circular-statistics derivation, retry and timeout handling, and the fallback for sparse stations.
- A real bug was caught and fixed during verification. It was not shipped silently.
  The first 30 s fetch timeout was too short for a station with a large
  history (`EUG`). Both sites would have silently fallen back to the same,
  farther station. They would not each have used their true nearest one. The
  bug was caught because the fallback distance (19.3 km) was worse than expected. No exception was raised. A script that does not crash can still give a wrong answer.
- `data/site/wind_rose.json` and `data/site_phytophthora/wind_rose.json` now
  exist, with real station data. Nothing in `pathogens.py` or `spread_engine.py`
  uses them yet. That is the separate Part B follow-on.
- Remaining for the next iteration: the directional, anisotropic dispersal
  kernel change (Part B of `wind_dispersal_and_soil_reweight.md`). This data unblocks it. Whoever picks it up should read the seasonal bimodality caveat above. Do this before treating `directionality_strength` as a simple confidence measure.
