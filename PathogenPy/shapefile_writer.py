"""
Minimal stdlib writer for an ESRI point shapefile plus its .dbf attribute
table, .prj, and .cpg. The write-direction counterpart to
shapefile_reader.py -- same format knowledge, no geopandas/fiona/pyshp,
no arcpy (see docs/notes/tree_point_export.md, Option B precedent from
docs/notes/site_tree_host_inventory.md).

Scope on purpose: points only, one fixed output CRS (EPSG:32610, the CRS
every site raster and the POS-derived inventory already use in this
project).
"""

import math
import struct
from pathlib import Path

import pandas as pd

SHAPE_TYPE_POINT = 1
SHP_HEADER_WORDS = 50   # 100-byte main-file / index-file header, in 16-bit words
SHP_RECORD_CONTENT_WORDS = 10  # shape type (4 bytes) + x + y (8 bytes each) = 20 bytes
SHX_ENTRY_WORDS = 4     # offset + content length, 4 bytes each

DBF_VERSION = 0x03
DBF_FIELD_TERMINATOR = 0x0D
DBF_RECORD_LIVE = 0x20  # ' ' -- not deleted

# WGS 1984 UTM Zone 10N -- the one CRS this project ever writes a point
# shapefile in. Quoted verbatim (same CRS arcpy.SpatialReference(32610)
# uses throughout arcpy_export/export_site_layers.py), not derived.
EPSG_32610_WKT = (
    'PROJCS["WGS_1984_UTM_Zone_10N",GEOGCS["GCS_WGS_1984",'
    'DATUM["D_WGS_1984",SPHEROID["WGS_1984",6378137.0,298.257223563]],'
    'PRIMEM["Greenwich",0.0],UNIT["Degree",0.0174532925199433]],'
    'PROJECTION["Transverse_Mercator"],PARAMETER["False_Easting",500000.0],'
    'PARAMETER["False_Northing",0.0],PARAMETER["Central_Meridian",-123.0],'
    'PARAMETER["Scale_Factor",0.9996],PARAMETER["Latitude_Of_Origin",0.0],'
    'UNIT["Meter",1.0]]'
)


def _write_shp_and_shx(shp_path, shx_path, records):
    n = len(records)
    xs = [r["x"] for r in records]
    ys = [r["y"] for r in records]
    xmin, xmax = (min(xs), max(xs)) if records else (0.0, 0.0)
    ymin, ymax = (min(ys), max(ys)) if records else (0.0, 0.0)

    shp_file_length_words = SHP_HEADER_WORDS + n * (4 + SHP_RECORD_CONTENT_WORDS)
    shx_file_length_words = SHP_HEADER_WORDS + n * SHX_ENTRY_WORDS

    def main_header(file_length_words):
        header = struct.pack(">i", 9994)          # file code
        header += b"\x00" * 20                    # 5 unused int32s
        header += struct.pack(">i", file_length_words)
        header += struct.pack("<i", 1000)          # version
        header += struct.pack("<i", SHAPE_TYPE_POINT)
        header += struct.pack("<4d", xmin, ymin, xmax, ymax)
        header += struct.pack("<4d", 0.0, 0.0, 0.0, 0.0)  # Z/M ranges, unused
        return header

    with open(shp_path, "wb") as shp, open(shx_path, "wb") as shx:
        shp.write(main_header(shp_file_length_words))
        shx.write(main_header(shx_file_length_words))

        offset_words = SHP_HEADER_WORDS
        for i, record in enumerate(records, start=1):
            shp.write(struct.pack(">ii", i, SHP_RECORD_CONTENT_WORDS))
            shp.write(struct.pack("<i", SHAPE_TYPE_POINT))
            shp.write(struct.pack("<2d", record["x"], record["y"]))

            shx.write(struct.pack(">ii", offset_words, SHP_RECORD_CONTENT_WORDS))
            offset_words += 4 + SHP_RECORD_CONTENT_WORDS


def _format_dbf_value(value, dbf_type, length, decimals):
    is_missing = value is None or (isinstance(value, float) and math.isnan(value)) or pd.isna(value)
    if dbf_type == "C":
        text = "" if is_missing else str(value)
        return text[:length].ljust(length)
    if dbf_type == "N":
        if is_missing:
            return " " * length
        return f"{float(value):.{decimals}f}"[:length].rjust(length)
    if dbf_type == "L":
        if is_missing:
            return " "
        return "T" if value else "F"
    raise ValueError(f"unsupported dbf_type {dbf_type!r}")


def _write_dbf(dbf_path, records, field_spec):
    record_length = 1 + sum(length for _, _, length, _ in field_spec)  # +1 deletion flag
    header_length = 32 + 32 * len(field_spec) + 1

    with open(dbf_path, "wb") as f:
        f.write(struct.pack("<B3B", DBF_VERSION, 1, 1, 1))  # version + fixed YY/MM/DD
        f.write(struct.pack("<I", len(records)))
        f.write(struct.pack("<HH", header_length, record_length))
        f.write(b"\x00" * 20)  # reserved

        for name, dbf_type, length, decimals in field_spec:
            name_bytes = name.encode("ascii")[:10].ljust(11, b"\x00")
            f.write(name_bytes)
            f.write(dbf_type.encode("ascii"))
            f.write(b"\x00" * 4)  # field data address, unused on write
            f.write(struct.pack("<BB", length, decimals))
            f.write(b"\x00" * 14)
        f.write(bytes([DBF_FIELD_TERMINATOR]))

        for record in records:
            f.write(bytes([DBF_RECORD_LIVE]))
            for name, dbf_type, length, decimals in field_spec:
                text = _format_dbf_value(record.get(name), dbf_type, length, decimals)
                f.write(text.encode("ascii", errors="replace"))
        f.write(b"\x1a")  # conventional end-of-file marker


def write_point_shapefile(path_stem, records, field_spec):
    """
    Writes a point shapefile (.shp/.shx/.dbf/.prj/.cpg) to path_stem.

    records: list of dicts, each {"x": float, "y": float, **attrs} where
        attrs keys match field_spec's dbf field names.
    field_spec: list of (dbf_field_name, dbf_type, length, decimals).
        dbf_field_name must be <= 10 characters. dbf_type is "C"
        (character), "N" (numeric), or "L" (logical/boolean). decimals
        is ignored for "C"/"L".
    """
    stem = Path(path_stem)
    if stem.suffix.lower() == ".shp":
        stem = stem.with_suffix("")
    stem.parent.mkdir(parents=True, exist_ok=True)

    _write_shp_and_shx(stem.with_suffix(".shp"), stem.with_suffix(".shx"), records)
    _write_dbf(stem.with_suffix(".dbf"), records, field_spec)

    with open(stem.with_suffix(".prj"), "w") as f:
        f.write(EPSG_32610_WKT)
    with open(stem.with_suffix(".cpg"), "w") as f:
        f.write("UTF-8")
