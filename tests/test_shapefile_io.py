from pathlib import Path
import struct
import sys

import pytest

sys.path.append(str(Path(__file__).resolve().parents[1] / "PathogenPy"))

from shapefile_reader import read_point_shapefile
from shapefile_writer import EPSG_32610_WKT, write_point_shapefile

FIELD_SPEC = [
    ("tree_id", "C", 12, 0),
    ("risk", "N", 10, 4),
    ("infected", "L", 1, 0),
]

RECORDS = [
    {"x": 493418.25, "y": 4871862.5, "tree_id": "POS1", "risk": 0.2138, "infected": True},
    {"x": 493500.0, "y": 4871900.75, "tree_id": "POS2", "risk": 0.0, "infected": False},
    {"x": 493610.5, "y": 4872010.0, "tree_id": "POS3", "risk": None, "infected": None},
]


def test_write_then_read_round_trip(tmp_path):
    stem = tmp_path / "points"
    write_point_shapefile(stem, RECORDS, FIELD_SPEC)

    features = read_point_shapefile(stem)

    assert len(features) == 3
    for feature, record in zip(features, RECORDS):
        assert feature["x"] == record["x"]
        assert feature["y"] == record["y"]
        assert feature["tree_id"] == record["tree_id"]
    assert float(features[0]["risk"]) == pytest.approx(0.2138)
    assert features[0]["infected"] == "T"
    assert features[1]["infected"] == "F"


def test_missing_values_are_written_blank(tmp_path):
    stem = tmp_path / "points"
    write_point_shapefile(stem, RECORDS, FIELD_SPEC)

    features = read_point_shapefile(stem)

    assert features[2]["risk"] == ""
    assert features[2]["infected"] == ""


def test_writer_creates_all_sidecar_files(tmp_path):
    stem = tmp_path / "nested" / "points"
    write_point_shapefile(stem, RECORDS, FIELD_SPEC)

    for suffix in (".shp", ".shx", ".dbf", ".prj", ".cpg"):
        assert stem.with_suffix(suffix).exists()
    assert stem.with_suffix(".prj").read_text() == EPSG_32610_WKT


def test_shp_header_length_and_bounding_box(tmp_path):
    stem = tmp_path / "points"
    write_point_shapefile(stem, RECORDS, FIELD_SPEC)

    raw = stem.with_suffix(".shp").read_bytes()
    file_code, = struct.unpack(">i", raw[0:4])
    length_words, = struct.unpack(">i", raw[24:28])
    xmin, ymin, xmax, ymax = struct.unpack("<4d", raw[36:68])

    assert file_code == 9994
    assert length_words * 2 == len(raw)
    assert (xmin, xmax) == (493418.25, 493610.5)
    assert (ymin, ymax) == (4871862.5, 4872010.0)


def test_reader_accepts_path_with_shp_suffix(tmp_path):
    stem = tmp_path / "points"
    write_point_shapefile(stem, RECORDS, FIELD_SPEC)

    features = read_point_shapefile(stem.with_suffix(".shp"))

    assert len(features) == 3


def test_reader_skips_null_shape_and_keeps_rows_aligned(tmp_path):
    stem = tmp_path / "points"
    write_point_shapefile(stem, RECORDS, FIELD_SPEC)

    # Change the shape type of the second record to 0 (null shape).
    # Layout: 100-byte header, then 28 bytes for each record (8 + 20).
    shp_path = stem.with_suffix(".shp")
    raw = bytearray(shp_path.read_bytes())
    second_record_content = 100 + 28 + 8
    raw[second_record_content:second_record_content + 4] = struct.pack("<i", 0)
    shp_path.write_bytes(bytes(raw))

    features = read_point_shapefile(stem)

    assert [f["tree_id"] for f in features] == ["POS1", "POS3"]
    assert features[1]["x"] == RECORDS[2]["x"]


def test_reader_skips_deleted_dbf_record(tmp_path):
    stem = tmp_path / "points"
    write_point_shapefile(stem, RECORDS[:1], FIELD_SPEC)

    dbf_path = stem.with_suffix(".dbf")
    raw = bytearray(dbf_path.read_bytes())
    header_length, = struct.unpack("<H", raw[8:10])
    raw[header_length] = 0x2A  # Deletion flag of the first record.
    dbf_path.write_bytes(bytes(raw))

    assert read_point_shapefile(stem) == []
