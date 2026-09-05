"""
Converts the engine's computed risk rasters (plain numpy arrays +
<basename>_grid_meta.json, written by run_real_site_risk_raster.py in the
arcpy-free venv) back into real georeferenced GeoTIFFs that can be loaded
into PathogenProject.aprx.

Run this under ArcGIS Pro's Python, after run_real_site_risk_raster.py has
produced the outputs/*.npy files:

    "C:\\Program Files\\ArcGIS\\Pro\\bin\\Python\\envs\\arcgispro-py3\\python.exe" ^
        import_risk_raster.py
"""

import json
from pathlib import Path

import arcpy
import numpy as np

OUTPUTS_DIR = Path(__file__).resolve().parent.parent.parent / "outputs"
TARGET_SR = arcpy.SpatialReference(32610)  # must match export_site_layers.py

# output basenames written by run_real_site_risk_raster.py
OUTPUT_BASENAMES = ["red_ring_rot_site_risk", "phytophthora_site_risk", "anthracnose_site_risk"]


def import_one(output_basename):
    risk_path = OUTPUTS_DIR / f"{output_basename}.npy"
    meta_path = OUTPUTS_DIR / f"{output_basename}_grid_meta.json"
    out_raster_path = str(OUTPUTS_DIR / f"{output_basename}.tif")

    if not risk_path.exists():
        print(f"SKIP (missing): {risk_path}")
        return

    with open(meta_path) as f:
        meta = json.load(f)

    risk = np.load(risk_path).astype(np.float32)
    # engine arrays are bottom-up (row 0 = origin_y); NumPyArrayToRaster
    # expects top-down (row 0 = north), matching RasterToNumPyArray.
    risk_top_down = np.flipud(risk)

    lower_left = arcpy.Point(meta["origin_x"], meta["origin_y"])
    raster = arcpy.NumPyArrayToRaster(
        risk_top_down, lower_left,
        x_cell_size=meta["resolution_m"], y_cell_size=meta["resolution_m"],
        value_to_nodata=-1,
    )
    arcpy.management.DefineProjection(raster, TARGET_SR)
    arcpy.management.CopyRaster(raster, out_raster_path)

    print(f"Wrote {out_raster_path}")


def main():
    arcpy.env.overwriteOutput = True
    for output_basename in OUTPUT_BASENAMES:
        import_one(output_basename)


if __name__ == "__main__":
    main()
