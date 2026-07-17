# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 SrednaBG Contributors
#
# SrednaBG — scrapers

"""Minimal MVT *encoder* for tests — the write-side counterpart of src.mvt.

Builds spec-compliant vector tiles from feature dicts so the decoder and the
TollTracker fetcher can be tested without binary fixtures.
"""

import struct


def _varint(value: int) -> bytes:
    out = bytearray()
    while True:
        bits = value & 0x7F
        value >>= 7
        if value:
            out.append(bits | 0x80)
        else:
            out.append(bits)
            return bytes(out)


def _tag(field: int, wire_type: int) -> bytes:
    return _varint((field << 3) | wire_type)


def _len_delimited(field: int, payload: bytes) -> bytes:
    return _tag(field, 2) + _varint(len(payload)) + payload


def _zigzag(value: int) -> int:
    # Python's arbitrary-precision ints make the canonical form sign-correct.
    return (value << 1) ^ (value >> 63)


def _encode_value(value) -> bytes:
    if isinstance(value, bool):
        return _tag(7, 0) + _varint(int(value))
    if isinstance(value, str):
        return _len_delimited(1, value.encode("utf-8"))
    if isinstance(value, int):
        if value >= 0:
            return _tag(5, 0) + _varint(value)  # uint64
        return _tag(6, 0) + _varint(_zigzag(value))  # sint64
    if isinstance(value, float):
        return _tag(3, 1) + struct.pack("<d", value)
    raise TypeError(f"unsupported property type {type(value)}")


def _encode_geometry(parts: list[list[tuple[int, int]]]) -> list[int]:
    commands: list[int] = []
    cx = cy = 0
    for part in parts:
        commands.append((1 << 3) | 1)  # MoveTo, count 1
        dx, dy = part[0][0] - cx, part[0][1] - cy
        commands.extend((_zigzag(dx), _zigzag(dy)))
        cx, cy = part[0]
        commands.append((len(part) - 1) << 3 | 2)  # LineTo, count n-1
        for x, y in part[1:]:
            commands.extend((_zigzag(x - cx), _zigzag(y - cy)))
            cx, cy = x, y
    return commands


def encode_tile(layers: dict[str, dict]) -> bytes:
    """Encode {layer_name: {"extent": int, "features": [...]}} into MVT bytes.

    Each feature is {"props": dict, "type": int, "parts": [[(x, y), ...]]}
    with integer tile-unit coordinates — the same shape src.mvt.decode returns.
    """
    tile = bytearray()
    for name, layer in layers.items():
        keys: list[str] = []
        values: list = []
        feature_bufs = []
        for feature in layer["features"]:
            tags: list[int] = []
            for k, v in feature["props"].items():
                if k not in keys:
                    keys.append(k)
                # No value dedup (True == 1 would collide) — tiles are tiny.
                values.append(v)
                tags.extend((keys.index(k), len(values) - 1))
            fbuf = bytearray()
            fbuf += _len_delimited(2, b"".join(_varint(t) for t in tags))
            fbuf += _tag(3, 0) + _varint(feature.get("type", 2))
            geometry = _encode_geometry(feature["parts"])
            fbuf += _len_delimited(4, b"".join(_varint(c) for c in geometry))
            feature_bufs.append(bytes(fbuf))

        lbuf = bytearray()
        lbuf += _tag(15, 0) + _varint(2)  # version
        lbuf += _len_delimited(1, name.encode("utf-8"))
        for fb in feature_bufs:
            lbuf += _len_delimited(2, fb)
        for k in keys:
            lbuf += _len_delimited(3, k.encode("utf-8"))
        for v in values:
            lbuf += _len_delimited(4, _encode_value(v))
        lbuf += _tag(5, 0) + _varint(layer.get("extent", 4096))
        tile += _len_delimited(3, bytes(lbuf))
    return bytes(tile)
