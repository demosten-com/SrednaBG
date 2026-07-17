# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 SrednaBG Contributors
#
# SrednaBG — scrapers

"""Minimal Mapbox Vector Tile (MVT) decoder and slippy-tile math.

Implements just enough of the MVT 2.1 spec (a protobuf wire format, frozen
since 2016) for the TollTracker fetcher to read polyline features out of a
public Mapbox tileset — property decoding and LineString geometry. Pure
stdlib, so the pipeline gains no protobuf/shapely dependency for one source.

Spec: https://github.com/mapbox/vector-tile-spec/tree/master/2.1
"""

import gzip
import math
import struct
from typing import Iterator

# Layer message fields
_LAYER_NAME = 1
_LAYER_FEATURE = 2
_LAYER_KEY = 3
_LAYER_VALUE = 4
_LAYER_EXTENT = 5

# Feature message fields
_FEATURE_ID = 1
_FEATURE_TAGS = 2
_FEATURE_TYPE = 3
_FEATURE_GEOMETRY = 4

# Geometry command opcodes
_CMD_MOVE_TO = 1
_CMD_LINE_TO = 2
_CMD_CLOSE_PATH = 7

DEFAULT_EXTENT = 4096


def _read_varint(buf: bytes, pos: int) -> tuple[int, int]:
    result = 0
    shift = 0
    while True:
        b = buf[pos]
        pos += 1
        result |= (b & 0x7F) << shift
        if not b & 0x80:
            return result, pos
        shift += 7


def _read_fields(buf: bytes) -> Iterator[tuple[int, int, int | bytes]]:
    """Yield (field_number, wire_type, value) over one protobuf message."""
    pos = 0
    end = len(buf)
    while pos < end:
        key, pos = _read_varint(buf, pos)
        field, wire_type = key >> 3, key & 7
        if wire_type == 0:  # varint
            val, pos = _read_varint(buf, pos)
        elif wire_type == 1:  # 64-bit
            val = buf[pos:pos + 8]
            pos += 8
        elif wire_type == 2:  # length-delimited
            length, pos = _read_varint(buf, pos)
            val = buf[pos:pos + length]
            pos += length
        elif wire_type == 5:  # 32-bit
            val = buf[pos:pos + 4]
            pos += 4
        else:
            raise ValueError(f"unsupported protobuf wire type {wire_type}")
        yield field, wire_type, val


def _zigzag(value: int) -> int:
    return (value >> 1) ^ -(value & 1)


def _decode_value(buf: bytes) -> str | float | int | bool | None:
    """Decode an MVT Value message (a oneof over the scalar types)."""
    for field, _wt, val in _read_fields(buf):
        if field == 1:
            return val.decode("utf-8")
        if field == 2:
            return struct.unpack("<f", val)[0]
        if field == 3:
            return struct.unpack("<d", val)[0]
        if field in (4, 5):  # int64 / uint64
            return val
        if field == 6:  # sint64
            return _zigzag(val)
        if field == 7:
            return bool(val)
    return None


def _decode_geometry(commands: list[int]) -> list[list[tuple[int, int]]]:
    """Decode an MVT geometry command stream into parts of (x, y) points.

    Coordinates are integer tile units relative to the layer extent; clipped
    geometry may extend outside [0, extent] into the tile buffer.
    """
    parts: list[list[tuple[int, int]]] = []
    current: list[tuple[int, int]] = []
    x = y = 0
    i = 0
    while i < len(commands):
        op, count = commands[i] & 7, commands[i] >> 3
        i += 1
        if op == _CMD_MOVE_TO:
            for _ in range(count):
                if current:
                    parts.append(current)
                    current = []
                x += _zigzag(commands[i])
                y += _zigzag(commands[i + 1])
                i += 2
                current.append((x, y))
        elif op == _CMD_LINE_TO:
            for _ in range(count):
                x += _zigzag(commands[i])
                y += _zigzag(commands[i + 1])
                i += 2
                current.append((x, y))
        elif op == _CMD_CLOSE_PATH:
            if current:
                current.append(current[0])
        else:
            raise ValueError(f"unknown geometry command {op}")
    if current:
        parts.append(current)
    return parts


def decode(data: bytes) -> dict[str, dict]:
    """Decode a vector tile into {layer_name: {"extent": int, "features": [...]}}.

    Each feature is {"props": dict, "type": int, "parts": [[(x, y), ...], ...]}
    with coordinates in integer tile units. Transparently gunzips.
    """
    if data[:2] == b"\x1f\x8b":
        data = gzip.decompress(data)

    layers: dict[str, dict] = {}
    for field, _wt, layer_buf in _read_fields(data):
        if field != 3:  # Tile.layers
            continue
        name = None
        extent = DEFAULT_EXTENT
        keys: list[str] = []
        values: list = []
        feature_bufs: list[bytes] = []
        for f, _w, v in _read_fields(layer_buf):
            if f == _LAYER_NAME:
                name = v.decode("utf-8")
            elif f == _LAYER_EXTENT:
                extent = v
            elif f == _LAYER_KEY:
                keys.append(v.decode("utf-8"))
            elif f == _LAYER_VALUE:
                values.append(_decode_value(v))
            elif f == _LAYER_FEATURE:
                feature_bufs.append(v)

        features = []
        for fbuf in feature_bufs:
            tags: list[int] = []
            gtype = 0
            commands: list[int] = []
            for f, _w, v in _read_fields(fbuf):
                if f == _FEATURE_TAGS:
                    pos = 0
                    while pos < len(v):
                        tag, pos = _read_varint(v, pos)
                        tags.append(tag)
                elif f == _FEATURE_TYPE:
                    gtype = v
                elif f == _FEATURE_GEOMETRY:
                    pos = 0
                    while pos < len(v):
                        cmd, pos = _read_varint(v, pos)
                        commands.append(cmd)
            props = {
                keys[tags[i]]: values[tags[i + 1]]
                for i in range(0, len(tags) - 1, 2)
            }
            features.append({
                "props": props,
                "type": gtype,
                "parts": _decode_geometry(commands),
            })
        if name is not None:
            layers[name] = {"extent": extent, "features": features}
    return layers


def lnglat_to_tile(lng: float, lat: float, zoom: int) -> tuple[float, float]:
    """Fractional slippy-tile coordinates of a WGS84 point."""
    n = 2 ** zoom
    x = (lng + 180.0) / 360.0 * n
    lat_r = math.radians(lat)
    y = (1.0 - math.log(math.tan(lat_r) + 1.0 / math.cos(lat_r)) / math.pi) / 2.0 * n
    return x, y


def tile_point_to_latlng(
    zoom: int, tx: int, ty: int, px: int, py: int, extent: int
) -> tuple[float, float]:
    """WGS84 (lat, lng) of an integer tile-unit point inside tile (tx, ty).

    Rounded to 7 decimals (~1 cm — far below tile-unit precision): the trig
    here goes through libm, whose last bits differ across platforms, and
    unrounded output would make the zones.json content hash machine-dependent
    (macOS refresh vs the Linux cron producing different hashes for
    identical upstream data).
    """
    n = 2 ** zoom
    x = (tx + px / extent) / n
    y = (ty + py / extent) / n
    lng = x * 360.0 - 180.0
    lat = math.degrees(math.atan(math.sinh(math.pi * (1.0 - 2.0 * y))))
    return round(lat, 7), round(lng, 7)


def tile_range(
    lat_min: float, lng_min: float, lat_max: float, lng_max: float, zoom: int
) -> Iterator[tuple[int, int]]:
    """Yield (x, y) of every tile at ``zoom`` intersecting the bounding box."""
    x0, y1 = lnglat_to_tile(lng_min, lat_min, zoom)
    x1, y0 = lnglat_to_tile(lng_max, lat_max, zoom)
    max_index = 2 ** zoom - 1
    for tx in range(max(0, int(x0)), min(max_index, int(x1)) + 1):
        for ty in range(max(0, int(y0)), min(max_index, int(y1)) + 1):
            yield tx, ty
