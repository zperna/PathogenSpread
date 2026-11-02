"""
Exports real site data from PathogenProject.gdb, gNATSGO_OR.gdb, the local
NLCD raster, and the ODF DEM image service. The output is flat, CRS-free
files. The arcpy-free engine venv reads these files.

Run this with ArcGIS Pro's Python. For example:

    "C:\\Program Files\\ArcGIS\\Pro\\bin\\Python\\envs\\arcgispro-py3\\python.exe" ^
        export_site_layers.py

See docs/feature_contracts/real_site_risk_raster.md and
docs/notes/real_site_risk_raster.md for why this script is separate from the
main engine. Only this script and import_risk_raster.py use arcpy.

All layers are reprojected to UTM Zone 10N (EPSG:32610, meters). The source
point layer and NLCD use Oregon Lambert *feet* (EPSG:2992). gNATSGO uses
Albers CONUS. The engine dispersal constants are in meters. The reprojection
happens here, once, not in the engine.

Output arrays are stored bottom-up (row 0 = origin_y/ymin). arcpy's
RasterToNumPyArray uses top-down order (row 0 = north). The plain-numpy
engine can index the arrays with simple (y - origin_y) / resolution_m math.

One AOI and grid are exported for each known-case feature class. Each grid
is centered on its own case(s). RedRingRot and Phytophthora are different
diseases at different real locations. Each gets its own 2 km site grid under
data/<site_name>/. The grids are not shared.
"""

import csv
import json
import math
from pathlib import Path

import arcpy
import numpy as np

PROJECT_DIR = Path(r"c:\Users\zakpe\Documents\GIS\Pathogen\PathogenProject")
PATHOGEN_GDB = str(PROJECT_DIR / "PathogenProject.gdb")
GNATSGO_GDB = str(PROJECT_DIR / "gNATSGO_OR.gdb")
NLCD_RASTER = str(PROJECT_DIR / "NLCD_2016_Land_Cover_OR" / "NLCD_2016_Land_Cover_OR.img")
DEM_SERVICE_URL = "https://gis.odf.oregon.gov/ags3/services/Basemaps/DEM_Enhanced_10meter_Oregon/ImageServer"

DATA_ROOT = Path(__file__).resolve().parent.parent.parent / "data"

TARGET_SR = arcpy.SpatialReference(32610)  # WGS 1984 UTM Zone 10N, meters
WGS84_SR = arcpy.SpatialReference(4326)  # for the AOI centroid lat/lon fed to fetch_wind_rose.py
CELL_SIZE_M = 10  # matches native gNATSGO/DEM resolution. NLCD (native 30m)
                   # is upsampled to this grid by nearest-neighbor.
                   # It is not resampled down.
AOI_HALF_SIZE_M = 1000  # 2 km square AOI centered on the known case(s)

# feature class name in PathogenProject.gdb -> output folder under data/
CASE_LAYERS = {
    "RedRingRot": "site",
    "Phytophthora": "site_phytophthora",
    "Anthracnose": "site_anthracnose",
}

DRAINAGE_CLASS_CODES = {
    "Excessively drained": 1,
    "Somewhat excessively drained": 2,
    "Well drained": 3,
    "Moderately well drained": 4,
    "Somewhat poorly drained": 5,
    "Poorly drained": 6,
    "Very poorly drained": 7,
}

HYDRO_GROUP_CODES = {
    "A": 1,  # well drained, low runoff/high infiltration
    "B": 2,
    "C": 3,
    "D": 4,  # poorly drained, high runoff/low infiltration
}

# muaggatt.wtdepannmin is NULL when no water table occurs within the
# reported depth range. NULL means "deep/not applicable", not missing data.
# NULL cells are filled with this sentinel (inches) before normalizing.
# This puts them near 0 suitability. They are not mistaken for "at the
# surface" (0in).
# Comfortably beyond any real value seen in either site AOI (max 76in).
WATER_TABLE_DEPTH_NODATA_SENTINEL_IN = 200

# Floor applied to slope (degrees) before computing tan(slope) for the
# topographic wetness index. tan(0) is 0. That would make the TWI ratio
# divide by zero at perfectly flat cells. 0.1 degrees is well below any real
# slope signal at this resolution. So it only affects genuinely flat cells.
# For those, a large (but now finite) TWI is directionally correct anyway.
TWI_MIN_SLOPE_DEG = 0.1

# Circular neighborhood radius (in cells) for the topographic position
# index focal mean. This is 150m at the current 10m CELL_SIZE_M. It was
# chosen to characterize local ridge or valley position, not macro-landform.
# It was also picked to numerically match red_ring_rot's
# max_dispersal_distance_m. See docs/notes/wind_exposure_index.md.
EXPOSURE_RADIUS_CELLS = 15


def read_known_cases(fc_name):
    """Reads a known-case point feature class.
    Reprojects it to the target CRS (meters).
    """
    fc = PATHOGEN_GDB + "\\" + fc_name
    fields = ["OID@", "SHAPE@", "tree_id", "species", "stress_index", "infected"]
    records = []
    with arcpy.da.SearchCursor(fc, fields) as cursor:
        for oid, shape, tree_id, species, stress_index, infected in cursor:
            projected = shape.projectAs(TARGET_SR)
            records.append({
                "tree_id": tree_id if tree_id is not None else f"SITE{oid:03d}",
                "x": projected.centroid.X,
                "y": projected.centroid.Y,
                "species": species,
                "stress_index": stress_index,
                "infected": str(infected).strip().lower() in ("yes", "true", "1"),
            })
    if not records:
        raise RuntimeError(f"{fc_name} feature class has no records to anchor the AOI on")
    return records


def build_aoi_extent(known_cases):
    xs = [r["x"] for r in known_cases]
    ys = [r["y"] for r in known_cases]
    cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    # Attach spatial_reference here. Do not rely only on
    # arcpy.env.outputCoordinateSystem, which is set later. Without it, ArcGIS
    # may read these meter coordinates in the wrong CRS. The result depends on
    # the order of environment settings. ArcGIS can then silently process the
    # entire input raster instead of clipping to the AOI.
    return arcpy.Extent(
        cx - AOI_HALF_SIZE_M, cy - AOI_HALF_SIZE_M,
        cx + AOI_HALF_SIZE_M, cy + AOI_HALF_SIZE_M,
        spatial_reference=TARGET_SR,
    )


def raster_to_bottom_up_array(raster_path, nodata_to_value=None):
    """RasterToNumPyArray is top-down (row 0 = north).
    Flip it so row 0 = south. This matches the engine's
    (y - origin_y) / resolution_m indexing.

    nodata_to_value fills NoData cells explicitly. Use it when the default
    NoData fill (0) collides with a real value that means something else.
    For example, water table depth, where 0 means "at the surface".
    """
    if nodata_to_value is None:
        arr = arcpy.RasterToNumPyArray(raster_path)
    else:
        arr = arcpy.RasterToNumPyArray(raster_path, nodata_to_value=nodata_to_value)
    return np.flipud(arr)


def export_land_cover(aoi_extent, reference_dir):
    arcpy.env.extent = aoi_extent
    arcpy.env.outputCoordinateSystem = TARGET_SR
    arcpy.env.cellSize = CELL_SIZE_M
    out_path = str(reference_dir / "landcover.tif")
    arcpy.management.ProjectRaster(
        NLCD_RASTER, out_path, TARGET_SR,
        resampling_type="NEAREST",  # categorical data
        cell_size=CELL_SIZE_M,
    )
    return out_path


def export_soil_surfaces(aoi_extent, reference_dir):
    """Joins MapunitRaster_10m's MUKEY to three muaggatt water and drainage
    attributes in one pass (drclassdcd, hydgrpdcd, wtdepannmin). Two of the
    three are categorical. The function reclassifies them to small integer
    codes. Then it reprojects and resamples all three. See
    docs/feature_contracts/soil_water_attributes.md for why these three
    specifically."""
    mapunit_raster = GNATSGO_GDB + r"\MapunitRaster_10m"
    muaggatt = GNATSGO_GDB + r"\muaggatt"

    working_raster = arcpy.env.scratchGDB + r"\mapunit_working"
    arcpy.management.CopyRaster(mapunit_raster, working_raster)
    arcpy.management.JoinField(
        working_raster, "MUKEY", muaggatt, "mukey",
        ["drclassdcd", "hydgrpdcd", "wtdepannmin"],
    )

    arcpy.management.AddField(working_raster, "drain_code", "SHORT")
    drain_code_block = "def code(name):\n    return {%s}.get(name, 0)" % ", ".join(
        f'"{name}": {code}' for name, code in DRAINAGE_CLASS_CODES.items()
    )
    arcpy.management.CalculateField(
        working_raster, "drain_code", "code(!drclassdcd!)", "PYTHON3", drain_code_block
    )

    arcpy.management.AddField(working_raster, "hydro_code", "SHORT")
    # Dual ratings (e.g. "A/D") give two groups. The first letter applies if
    # the soil is artificially drained. The second letter applies under
    # natural conditions. This project has no engineered drainage data. So
    # the code uses the natural (second-letter) rating.
    hydro_code_block = "def code(group):\n" \
        "    if not group:\n" \
        "        return 0\n" \
        "    natural = group.split('/')[-1].strip()\n" \
        "    return {%s}.get(natural, 0)" % ", ".join(
            f'"{name}": {code}' for name, code in HYDRO_GROUP_CODES.items()
        )
    arcpy.management.CalculateField(
        working_raster, "hydro_code", "code(!hydgrpdcd!)", "PYTHON3", hydro_code_block
    )

    drain_lookup = arcpy.sa.Lookup(working_raster, "drain_code")
    hydro_lookup = arcpy.sa.Lookup(working_raster, "hydro_code")
    wtdepth_lookup = arcpy.sa.Lookup(working_raster, "wtdepannmin")

    arcpy.env.extent = aoi_extent
    arcpy.env.outputCoordinateSystem = TARGET_SR
    arcpy.env.cellSize = CELL_SIZE_M

    outputs = {}
    for name, raster in [
        ("soil_drainage", drain_lookup),
        ("soil_hydro_group", hydro_lookup),
        ("soil_water_table_depth", wtdepth_lookup),
    ]:
        out_path = str(reference_dir / f"{name}.tif")
        arcpy.management.ProjectRaster(
            raster, out_path, TARGET_SR,
            resampling_type="NEAREST",  # categorical / piecewise-constant-per-mapunit data
            cell_size=CELL_SIZE_M,
        )
        outputs[name] = out_path

    arcpy.management.Delete(working_raster)
    return outputs


def export_terrain(aoi_extent, reference_dir):
    """Pulls a permanent local DEM clip from the live ODF image service.
    It then derives Slope, Aspect, a topographic wetness index, and a topographic
    position index from that local copy. It does not use the live service for
    these. See docs/feature_contracts/topographic_wetness_index.md and
    docs/feature_contracts/wind_exposure_index.md. They explain why TWI and TPI
    are exported with slope and aspect, not in place of them."""
    # The service does not expose its SR through a plain Describe(url) or
    # ProjectRaster call. So Clip cannot use aoi_extent's meter coordinates
    # directly. The service uses EPSG:2992. This was confirmed from the
    # layer as loaded in PathogenProject.aprx. Reproject the AOI corners into
    # that CRS (feet). Then Clip can cut the service down before anything
    # else uses it.
    service_sr = arcpy.SpatialReference(2992)
    lower_left = arcpy.PointGeometry(arcpy.Point(aoi_extent.XMin, aoi_extent.YMin), TARGET_SR).projectAs(service_sr).firstPoint
    upper_right = arcpy.PointGeometry(arcpy.Point(aoi_extent.XMax, aoi_extent.YMax), TARGET_SR).projectAs(service_sr).firstPoint
    rectangle = f"{lower_left.X} {lower_left.Y} {upper_right.X} {upper_right.Y}"

    # Env settings left over from the land cover and soil exports can break
    # this step. These are extent, outputCoordinateSystem, and cellSize. They
    # use a different CRS and extent than the DEM service. With them set, this
    # Clip call against the live service hangs indefinitely instead of
    # returning in a few seconds. Reset them first.
    arcpy.env.extent = None
    arcpy.env.outputCoordinateSystem = None
    arcpy.env.cellSize = None

    dem_raw = arcpy.env.scratchGDB + r"\dem_raw"
    arcpy.management.Clip(DEM_SERVICE_URL, rectangle, dem_raw, maintain_clipping_extent="NO_MAINTAIN_EXTENT")
    arcpy.management.DefineProjection(dem_raw, service_sr)

    arcpy.env.extent = aoi_extent
    arcpy.env.outputCoordinateSystem = TARGET_SR
    arcpy.env.cellSize = CELL_SIZE_M

    dem_local = str(reference_dir / "dem.tif")
    arcpy.management.ProjectRaster(
        dem_raw, dem_local, TARGET_SR,
        resampling_type="BILINEAR",
        cell_size=CELL_SIZE_M,
    )

    slope_raster = arcpy.sa.Slope(dem_local, output_measurement="DEGREE")
    slope_path = str(reference_dir / "slope.tif")
    aspect_path = str(reference_dir / "aspect.tif")
    slope_raster.save(slope_path)
    arcpy.sa.Aspect(dem_local).save(aspect_path)

    # Topographic wetness index: ln(specific_catchment_area / tan(slope)).
    # Fill -> FlowDirection -> FlowAccumulation is the standard prerequisite
    # chain. It uses D8, the Spatial Analyst default. The chain derives
    # contributing area from a DEM.
    filled_dem = arcpy.sa.Fill(dem_local)
    flow_direction = arcpy.sa.FlowDirection(filled_dem)
    flow_accumulation = arcpy.sa.FlowAccumulation(flow_direction)
    # +1 counts the cell's own unit contribution. This is the standard
    # convention. It also avoids a zero specific catchment area at ridge cells
    # (flow accumulation 0).
    specific_catchment_area = (flow_accumulation + 1) * CELL_SIZE_M
    slope_deg_clamped = arcpy.sa.Con(slope_raster < TWI_MIN_SLOPE_DEG, TWI_MIN_SLOPE_DEG, slope_raster)
    slope_radians = slope_deg_clamped * (math.pi / 180)
    wetness_index = arcpy.sa.Ln(specific_catchment_area / arcpy.sa.Tan(slope_radians))
    wetness_path = str(reference_dir / "wetness_index.tif")
    wetness_index.save(wetness_path)

    # Topographic position index: elevation relative to the local
    # neighborhood mean. Positive = ridge/convex (more wind-exposed).
    # Negative = valley/concave (sheltered). ignore_nodata=True (the default)
    # lets the focal mean compute near the AOI edge. It uses whatever valid
    # cells fall in the window. So this step does not widen the NoData band
    # beyond what the source DEM already has.
    neighborhood = arcpy.sa.NbrCircle(EXPOSURE_RADIUS_CELLS, "CELL")
    focal_mean_elevation = arcpy.sa.FocalStatistics(dem_local, neighborhood, "MEAN")
    exposure_index = arcpy.sa.Raster(dem_local) - focal_mean_elevation
    exposure_path = str(reference_dir / "exposure_index.tif")
    exposure_index.save(exposure_path)

    return slope_path, aspect_path, wetness_path, exposure_path


def export_case_layer(fc_name, site_name):
    out_dir = DATA_ROOT / site_name
    reference_dir = out_dir / "gis_reference"
    out_dir.mkdir(parents=True, exist_ok=True)
    reference_dir.mkdir(parents=True, exist_ok=True)

    known_cases = read_known_cases(fc_name)
    aoi_extent = build_aoi_extent(known_cases)

    landcover_path = export_land_cover(aoi_extent, reference_dir)
    soil_paths = export_soil_surfaces(aoi_extent, reference_dir)
    slope_path, aspect_path, wetness_path, exposure_path = export_terrain(aoi_extent, reference_dir)

    landcover_arr = raster_to_bottom_up_array(landcover_path)
    soil_arr = raster_to_bottom_up_array(soil_paths["soil_drainage"])
    hydro_arr = raster_to_bottom_up_array(soil_paths["soil_hydro_group"])
    wtdepth_arr = raster_to_bottom_up_array(
        soil_paths["soil_water_table_depth"], nodata_to_value=WATER_TABLE_DEPTH_NODATA_SENTINEL_IN
    )
    # Slope, Aspect, TWI, and TPI are float rasters with a real NoData edge.
    # DEM reprojection leaves a thin NoData band at the AOI boundary. Bilinear
    # resampling had no source coverage there. RasterToNumPyArray's default
    # float NoData fill is the dtype's min or max representable value
    # (~+/-3.4e38). That fill silently breaks downstream min-max
    # normalization if it is not caught. NaN makes these cells explicit
    # instead. spatial_inputs.py handles them
    # (score_terrain / load_site_grid).
    slope_arr = raster_to_bottom_up_array(slope_path, nodata_to_value=np.nan)
    aspect_arr = raster_to_bottom_up_array(aspect_path, nodata_to_value=np.nan)
    wetness_arr = raster_to_bottom_up_array(wetness_path, nodata_to_value=np.nan)
    exposure_arr = raster_to_bottom_up_array(exposure_path, nodata_to_value=np.nan)

    layers = {
        "landcover": landcover_arr, "soil": soil_arr, "hydro": hydro_arr,
        "wtdepth": wtdepth_arr, "slope": slope_arr, "aspect": aspect_arr,
        "wetness": wetness_arr, "exposure": exposure_arr,
    }
    shapes = {name: arr.shape for name, arr in layers.items()}
    if len(set(shapes.values())) != 1:
        # Each layer comes from a different source CRS. NLCD uses a feet-based
        # grid. The soil and DEM sources are Albers or feet-based. Reprojection
        # puts each output on a slightly different pixel phase, even for the
        # same real-world extent. So row and column counts can differ by a few
        # cells. All layers share the same origin (bottom-left) corner. They
        # were all clipped with the same aoi_extent. So it is safe to crop from
        # that corner to the common shape. The script crops instead of failing.
        n_rows = min(s[0] for s in shapes.values())
        n_cols = min(s[1] for s in shapes.values())
        print(f"[{fc_name}] Layer grids not pixel-aligned ({shapes}) -- cropping all to ({n_rows}, {n_cols}) from the origin corner")
        landcover_arr = landcover_arr[:n_rows, :n_cols]
        soil_arr = soil_arr[:n_rows, :n_cols]
        hydro_arr = hydro_arr[:n_rows, :n_cols]
        wtdepth_arr = wtdepth_arr[:n_rows, :n_cols]
        slope_arr = slope_arr[:n_rows, :n_cols]
        aspect_arr = aspect_arr[:n_rows, :n_cols]
        wetness_arr = wetness_arr[:n_rows, :n_cols]
        exposure_arr = exposure_arr[:n_rows, :n_cols]

    n_rows, n_cols = landcover_arr.shape
    np.save(out_dir / "landcover.npy", landcover_arr)
    np.save(out_dir / "soil_drain_code.npy", soil_arr)
    np.save(out_dir / "hydro_group_code.npy", hydro_arr)
    np.save(out_dir / "water_table_depth_in.npy", wtdepth_arr)
    np.save(out_dir / "slope_degrees.npy", slope_arr)
    np.save(out_dir / "aspect_degrees.npy", aspect_arr)
    np.save(out_dir / "wetness_index.npy", wetness_arr)
    np.save(out_dir / "exposure_index.npy", exposure_arr)

    with open(out_dir / "drainage_classes.json", "w") as f:
        json.dump({code: name for name, code in DRAINAGE_CLASS_CODES.items()}, f, indent=2)

    with open(out_dir / "hydro_groups.json", "w") as f:
        json.dump({code: name for name, code in HYDRO_GROUP_CODES.items()}, f, indent=2)

    # Centroid lat/lon, for the nearest-station lookup in fetch_wind_rose.py.
    # It is computed here because arcpy is available here. The plain venv has
    # no pyproj or arcpy, so it cannot do this projection itself.
    centroid = arcpy.PointGeometry(
        arcpy.Point((aoi_extent.XMin + aoi_extent.XMax) / 2, (aoi_extent.YMin + aoi_extent.YMax) / 2),
        TARGET_SR,
    ).projectAs(WGS84_SR).firstPoint

    grid_meta = {
        "origin_x": aoi_extent.XMin,
        "origin_y": aoi_extent.YMin,
        "resolution_m": CELL_SIZE_M,
        "n_rows": n_rows,
        "n_cols": n_cols,
        "area_size_m": max(n_rows, n_cols) * CELL_SIZE_M,
        "crs": "EPSG:32610",
        "array_row_convention": "bottom-up (row 0 = origin_y)",
        "centroid_lat": centroid.Y,
        "centroid_lon": centroid.X,
    }
    with open(out_dir / "grid_meta.json", "w") as f:
        json.dump(grid_meta, f, indent=2)

    with open(out_dir / "known_cases.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["tree_id", "x", "y", "species", "stress_index", "infected"])
        writer.writeheader()
        writer.writerows(known_cases)

    print(f"[{fc_name}] Exported {n_rows}x{n_cols} grid at {CELL_SIZE_M}m resolution to {out_dir}")
    print(f"[{fc_name}] Known cases: {len(known_cases)}")
    print(f"[{fc_name}] GIS-reference GeoTIFFs written to {reference_dir}")


def main():
    arcpy.env.overwriteOutput = True
    arcpy.CheckOutExtension("Spatial")

    for fc_name, site_name in CASE_LAYERS.items():
        export_case_layer(fc_name, site_name)


if __name__ == "__main__":
    main()
