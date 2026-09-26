"""
Minimal stdlib reader for an ESRI point shapefile plus its .dbf attribute
table. No geopandas / fiona / pyshp -- the plain engine .venv has none of
them and the POS tree layer is a static local file, not a live service
(see docs/notes/site_tree_host_inventory.md, Option B).

Scope on purpose:
- Point shapefiles only (shape type 1). Null shapes (type 0) are skipped;
  the POS file has one.
- dBASE III/IV .dbf: character and numeric fields read as stripped text.
  Deleted records (flag 0x2A) are skipped.
- Field text decoded latin1 so no byte sequence can raise. The .cpg may
  claim UTF-8, but callers here only read ASCII-safe leading tokens
  (genus, site_typ, diameter digits), so this is the safe choice -- see
  the note in docs/notes/site_tree_host_inventory.md.
"""

import struct
from pathlib import Path

SHAPE_TYPE_NULL = 0
SHAPE_TYPE_POINT = 1

DBF_FIELD_TERMINATOR = 0x0D
DBF_RECORD_DELETED = 0x2A  # '*'


def _read_dbf(dbf_path):
    """Yields one dict of {field_name: stripped_text} per live record."""
    with open(dbf_path, "rb") as f:
        header = f.read(32)
        record_count, header_length, record_length = struct.unpack("<IHH", header[4:12])

        fields = []  # (name, length)
        while True:
            descriptor = f.read(32)
            if not descriptor or descriptor[0] == DBF_FIELD_TERMINATOR:
                break
            name = descriptor[:11].split(b"\x00")[0].decode("latin1")
            length = descriptor[16]
            fields.append((name, length))

        f.seek(header_length)
        for _ in range(record_count):
            record = f.read(record_length)
            if len(record) < record_length:
                break
            if record[0] == DBF_RECORD_DELETED:
                continue
            offset = 1
            row = {}
            for name, length in fields:
                row[name] = record[offset:offset + length].decode("latin1").strip()
                offset += length
            yield row


def _read_shp_points(shp_path):
    """Yields (x, y) or None (null shape) per record, in file order."""
    with open(shp_path, "rb") as f:
        f.read(100)  # fixed-size main-file header
        while True:
            record_header = f.read(8)
            if len(record_header) < 8:
                break
            # record number + content length, both big-endian, length in
            # 16-bit words
            _, content_length_words = struct.unpack(">ii", record_header)
            content = f.read(content_length_words * 2)
            shape_type = struct.unpack("<i", content[:4])[0]
            if shape_type == SHAPE_TYPE_POINT:
                x, y = struct.unpack("<2d", content[4:20])
                yield (x, y)
            else:
                yield None


def read_point_shapefile(path_stem):
    """
    Reads a point shapefile + .dbf into a list of dicts, one per feature:
    {"x": float, "y": float, **dbf_fields}.

    path_stem is the path without extension (or with .shp -- both work).
    Records whose geometry is a null shape are dropped, keeping .shp and
    .dbf row alignment by skipping the matching attribute row too.
    """
    stem = Path(path_stem)
    if stem.suffix.lower() == ".shp":
        stem = stem.with_suffix("")
    shp_path = stem.with_suffix(".shp")
    dbf_path = stem.with_suffix(".dbf")

    features = []
    for point, attributes in zip(_read_shp_points(shp_path), _read_dbf(dbf_path)):
        if point is None:
            continue
        features.append({"x": point[0], "y": point[1], **attributes})
    return features
