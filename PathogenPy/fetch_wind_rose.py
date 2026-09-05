"""
Looks up the nearest Oregon ASOS/AWOS weather station to each site's AOI
centroid and derives a prevailing wind direction + directionality strength
from its historical wind rose, via the Iowa Environmental Mesonet (IEM)'s
public API (see docs/feature_contracts/real_wind_data.md for why IEM,
despite the name, and docs/notes/real_wind_data.md for the parsing/circular-
statistics details).

Run with the plain project .venv -- no arcpy required, just stdlib
urllib. Requires each data/<site_name>/grid_meta.json to already have
centroid_lat/centroid_lon (written by export_site_layers.py under Pro's
Python).

This produces data/<site_name>/wind_rose.json, which
run_real_site_risk_raster.py feeds into spread_engine.py's wind-aware
dispersal kernel for airborne/vector-transmitted pathogens -- see
docs/feature_contracts/wind_dispersal_and_soil_reweight.md Part B.
"""

import json
import math
import re
import urllib.error
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_ROOT = PROJECT_ROOT / "data"

IEM_BASE = "https://mesonet.agron.iastate.edu"
NETWORK = "OR_ASOS"  # all current sites are Oregon AOIs -- see contract non-goals

# Below this many historical observations, treat a station as too sparse to
# trust and fall back to the next-nearest one -- a station being listed in
# the network doesn't guarantee it has a usable long-term record.
MIN_OBSERVATION_COUNT = 1000

SITE_NAMES = ["site", "site_phytophthora", "site_anthracnose"]


def haversine_km(lat1, lon1, lat2, lon2):
    r_km = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlon / 2) ** 2
    return 2 * r_km * math.asin(math.sqrt(a))


def fetch_json(url):
    with urllib.request.urlopen(url, timeout=30) as resp:
        return json.load(resp)


def fetch_text(url):
    # A station with a long historical record (e.g. EUG, 597k observations
    # since 1948) can take ~45s server-side to aggregate for justdata=true
    # -- confirmed by direct timing, not a flaky connection -- so this
    # needs a longer timeout than a typical JSON metadata call.
    with urllib.request.urlopen(url, timeout=120) as resp:
        return resp.read().decode("utf-8")


def list_stations_by_distance(lat, lon):
    """Returns [(distance_km, station_id, station_name), ...] sorted nearest-first."""
    geojson = fetch_json(f"{IEM_BASE}/geojson/network.py?network={NETWORK}")
    stations = []
    for feature in geojson["features"]:
        props = feature["properties"]
        station_lon, station_lat = feature["geometry"]["coordinates"][:2]
        distance_km = haversine_km(lat, lon, station_lat, station_lon)
        stations.append((distance_km, props["sid"], props.get("sname", props["sid"])))
    stations.sort(key=lambda row: row[0])
    return stations


def parse_wind_rose_table(raw_text):
    """Parses IEM's justdata=true wind rose table into per-sector total
    frequencies (speed bins summed, calm excluded) plus the station-wide
    calm percent and observation count.

    Table quirk (confirmed against the raw response, not a summary of it):
    only the *first* data row's Calm column is populated -- it's a
    station-wide scalar placed there for tabular convenience, not a value
    for that row's own direction sector.
    """
    observation_count = None
    calm_percent = None
    sector_frequencies = {}

    lines = raw_text.splitlines()
    header_seen = False
    for line in lines:
        if line.startswith("#"):
            match = re.search(r"Observations Used/Missing/Total:\s*(\d+)", line)
            if match:
                observation_count = int(match.group(1))
            continue
        if not line.strip():
            continue
        if not header_seen:
            header_seen = True  # first non-comment line is the column header, skip it
            continue

        fields = [f.strip() for f in line.split(",")]
        if len(fields) < 8:
            print(f"  Skipping malformed wind rose row: {line!r}")
            continue

        direction_label = fields[0]
        if fields[1]:
            calm_percent = float(fields[1])

        speed_bin_values = [float(f) for f in fields[2:8] if f]
        sector_frequencies[direction_label] = sum(speed_bin_values)

    return observation_count, calm_percent, sector_frequencies


def circular_direction_and_strength(sector_frequencies):
    """Mean resultant direction/length of the per-sector frequency
    distribution -- see docs/notes/real_wind_data.md for why this instead
    of just taking the max-frequency sector."""
    sin_sum = 0.0
    cos_sum = 0.0
    total_freq = 0.0
    for label, freq in sector_frequencies.items():
        center_deg = (int(label[:3]) + 5) % 360
        sin_sum += freq * math.sin(math.radians(center_deg))
        cos_sum += freq * math.cos(math.radians(center_deg))
        total_freq += freq

    prevailing_direction_deg = math.degrees(math.atan2(sin_sum, cos_sum)) % 360
    directionality_strength = math.sqrt(sin_sum**2 + cos_sum**2) / total_freq
    return prevailing_direction_deg, directionality_strength


def fetch_wind_rose_for_site(site_name):
    data_dir = DATA_ROOT / site_name
    with open(data_dir / "grid_meta.json") as f:
        meta = json.load(f)

    lat, lon = meta["centroid_lat"], meta["centroid_lon"]
    stations = list_stations_by_distance(lat, lon)

    for distance_km, station_id, station_name in stations:
        url = f"{IEM_BASE}/cgi-bin/mywindrose.py?station={station_id}&network={NETWORK}&justdata=true"
        raw_text = None
        for attempt in range(3):
            try:
                raw_text = fetch_text(url)
                break
            except (urllib.error.URLError, OSError) as e:
                print(f"[{site_name}] {station_id}: fetch attempt {attempt + 1} failed ({e})")
        if raw_text is None:
            print(f"[{site_name}] {station_id}: gave up after 3 attempts, trying next station")
            continue

        observation_count, calm_percent, sector_frequencies = parse_wind_rose_table(raw_text)
        if not observation_count or observation_count < MIN_OBSERVATION_COUNT or not sector_frequencies:
            print(f"[{site_name}] {station_id}: only {observation_count or 0} observations, trying next station")
            continue

        prevailing_direction_deg, directionality_strength = circular_direction_and_strength(sector_frequencies)

        wind_rose = {
            "station_id": station_id,
            "station_name": station_name,
            "distance_km": round(distance_km, 1),
            "observation_count": observation_count,
            "calm_percent": calm_percent,
            "prevailing_direction_deg": round(prevailing_direction_deg, 1),
            "directionality_strength": round(directionality_strength, 3),
            "sector_frequencies": sector_frequencies,
        }
        with open(data_dir / "wind_rose.json", "w") as f:
            json.dump(wind_rose, f, indent=2)

        print(f"[{site_name}] {station_id} ({station_name}), {distance_km:.1f} km, "
              f"{observation_count} obs: prevailing {prevailing_direction_deg:.1f} deg, "
              f"strength {directionality_strength:.3f}")
        return

    raise RuntimeError(f"[{site_name}] No station near ({lat}, {lon}) had a usable wind record")


def main():
    for site_name in SITE_NAMES:
        fetch_wind_rose_for_site(site_name)


if __name__ == "__main__":
    main()
