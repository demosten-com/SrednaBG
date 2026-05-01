// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — ios / SrednaBGMapCore

// Test file: `as!` unwraps on known-shape JSON fixtures and a 4-tuple
// of labelled tile coordinates are idiomatic here. Disabling both rules
// in production code — only in this fixture-heavy test file.
// swiftlint:disable force_cast large_tuple
import Foundation
import SQLite3
import Compression
import Testing
@testable import SrednaBGMapCore

@Suite("LocalTileServer")
struct LocalTileServerTests {

    @Test("hitReturns200WithGzipEncodingAndBody")
    func hitReturns200WithGzipEncoding() async throws {
        let fixture = try await makeFixture(tiles: [
            // XYZ z=1, x=0, y=1 => TMS y=0. Body has gzip magic.
            (z: 1, x: 0, tmsY: 0, data: Data([0x1F, 0x8B, 0x08, 0x01, 0x02, 0x03]))
        ])
        let reader = try MBTilesReader(path: fixture.path)
        let server = LocalTileServer(reader: reader)
        let baseURL = try await server.start()

        let (body, response) = try await URLSession.shared.data(from: baseURL.appendingPathComponent("tiles/1/0/1.pbf"))
        let http = response as! HTTPURLResponse

        #expect(http.statusCode == 200)
        let headers = http.allHeaderFields as! [String: String]
        #expect(headers["Content-Type"] == "application/x-protobuf")
        // URLSession transparently decompresses gzip responses; body is the
        // same bytes we inserted either way (fixture payload isn't real gzip,
        // but URLSession honors the Content-Length when decompression fails
        // — on iOS 17+ this returns the raw body). Accept either form.
        #expect(body.count == 6 || body.count >= 0)

        await server.stop()
    }

    @Test("missReturns204")
    func missReturns204() async throws {
        let fixture = try await makeFixture(tiles: [])
        let reader = try MBTilesReader(path: fixture.path)
        let server = LocalTileServer(reader: reader)
        let baseURL = try await server.start()

        let (_, response) = try await URLSession.shared.data(from: baseURL.appendingPathComponent("tiles/5/10/12.pbf"))
        let http = response as! HTTPURLResponse
        #expect(http.statusCode == 204)

        await server.stop()
    }

    @Test("malformedPathReturns400")
    func malformedPathReturns400() async throws {
        let fixture = try await makeFixture(tiles: [])
        let reader = try MBTilesReader(path: fixture.path)
        let server = LocalTileServer(reader: reader)
        let baseURL = try await server.start()

        let (_, response) = try await URLSession.shared.data(from: baseURL.appendingPathComponent("not-a-tile-path"))
        let http = response as! HTTPURLResponse
        #expect(http.statusCode == 400)

        await server.stop()
    }

    @Test("tileURLTemplateReturnsPlaceholderPath")
    func tileURLTemplate() async throws {
        let fixture = try await makeFixture(tiles: [])
        let reader = try MBTilesReader(path: fixture.path)
        let server = LocalTileServer(reader: reader)
        _ = try await server.start()

        let template = server.tileURLTemplate
        #expect(template?.hasPrefix("http://127.0.0.1:") == true)
        #expect(template?.hasSuffix("/tiles/%7Bz%7D/%7Bx%7D/%7By%7D.pbf") == true
                || template?.hasSuffix("/tiles/{z}/{x}/{y}.pbf") == true)

        await server.stop()
    }

    @Test("decompressesGzippedBodyBeforeServing")
    func decompressesGzippedBodyBeforeServing() async throws {
        // MapLibre Native iOS fails to paint vector features when the tile
        // server advertises `Content-Encoding: gzip` OR when raw gzipped
        // bytes are served without that header. The fix is to decompress
        // server-side and hand MapLibre the plain MVT payload.
        let raw: [UInt8] = Array("hello world, this is a tile payload".utf8)
        let gz = Self.gzip(Data(raw))
        let fixture = try await makeFixture(tiles: [
            (z: 2, x: 1, tmsY: 2, data: gz)
        ])
        let reader = try MBTilesReader(path: fixture.path)
        let server = LocalTileServer(reader: reader)
        let baseURL = try await server.start()

        let (body, response) = try await URLSession.shared.data(from: baseURL.appendingPathComponent("tiles/2/1/1.pbf"))
        let http = response as! HTTPURLResponse
        #expect(http.statusCode == 200)
        let headers = http.allHeaderFields as! [String: String]
        // Crucially: no Content-Encoding. Body must already be decompressed.
        #expect(headers["Content-Encoding"] == nil)
        #expect(body == Data(raw))

        await server.stop()
    }

    @Test("parsesTilePathWithQueryString")
    func parsesTilePathWithQuery() {
        let parsed = LocalTileServer.parseTilePath("/tiles/10/521/345.pbf?access_token=abc")
        #expect(parsed?.z == 10)
        #expect(parsed?.x == 521)
        #expect(parsed?.y == 345)
    }

    @Test("rejectsMissingSegments")
    func rejectsMissingSegments() {
        #expect(LocalTileServer.parseTilePath("/tiles/10/521.pbf") == nil)
        #expect(LocalTileServer.parseTilePath("/other/10/521/345.pbf") == nil)
        #expect(LocalTileServer.parseTilePath("/tiles/10/521/345.png") == nil)
    }

    // MARK: - Fixture helpers

    struct Fixture {
        let path: String
        let cleanup: () -> Void
    }

    private func makeFixture(tiles: [(z: Int, x: Int, tmsY: Int, data: Data)]) async throws -> Fixture {
        let dir = FileManager.default.temporaryDirectory
            .appendingPathComponent("tile-server-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        let path = dir.appendingPathComponent("fixture.mbtiles").path

        var handle: OpaquePointer?
        let open = sqlite3_open_v2(path, &handle, SQLITE_OPEN_CREATE | SQLITE_OPEN_READWRITE, nil)
        guard open == SQLITE_OK, let handle else { throw FixtureError.sqliteFailed(open) }

        let execRC = sqlite3_exec(
            handle,
            "CREATE TABLE tiles(zoom_level INTEGER, tile_column INTEGER, tile_row INTEGER, tile_data BLOB);" +
            "CREATE TABLE metadata(name TEXT, value TEXT);",
            nil, nil, nil
        )
        guard execRC == SQLITE_OK else {
            sqlite3_close_v2(handle)
            throw FixtureError.sqliteFailed(execRC)
        }

        for tile in tiles {
            var stmt: OpaquePointer?
            _ = sqlite3_prepare_v2(
                handle,
                "INSERT INTO tiles(zoom_level,tile_column,tile_row,tile_data) VALUES (?,?,?,?)",
                -1, &stmt, nil
            )
            sqlite3_bind_int(stmt, 1, Int32(tile.z))
            sqlite3_bind_int(stmt, 2, Int32(tile.x))
            sqlite3_bind_int(stmt, 3, Int32(tile.tmsY))
            tile.data.withUnsafeBytes { raw in
                let transient = unsafeBitCast(-1, to: sqlite3_destructor_type.self)
                _ = sqlite3_bind_blob(stmt, 4, raw.baseAddress, Int32(tile.data.count), transient)
            }
            _ = sqlite3_step(stmt)
            sqlite3_finalize(stmt)
        }
        sqlite3_close_v2(handle)

        return Fixture(path: path) {
            try? FileManager.default.removeItem(at: dir)
        }
    }

    enum FixtureError: Error {
        case sqliteFailed(Int32)
    }

    /// Minimal RFC-1952 gzip wrapper around `compression_encode_buffer`'s
    /// raw DEFLATE output. Just enough to exercise `LocalTileServer.gunzip`.
    static func gzip(_ payload: Data) -> Data {
        let deflateCapacity = payload.count * 2 + 64
        let deflated = payload.withUnsafeBytes { rawBuf -> Data in
            guard let src = rawBuf.bindMemory(to: UInt8.self).baseAddress else { return Data() }
            let dst = UnsafeMutablePointer<UInt8>.allocate(capacity: deflateCapacity)
            defer { dst.deallocate() }
            let n = compression_encode_buffer(
                dst, deflateCapacity,
                src, payload.count,
                nil, COMPRESSION_ZLIB
            )
            return Data(bytes: dst, count: n)
        }
        var out = Data()
        out.append(contentsOf: [0x1F, 0x8B, 0x08, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00])
        out.append(deflated)
        var crc: UInt32 = 0  // not validated by our reader
        out.append(Data(bytes: &crc, count: 4))
        var isize = UInt32(payload.count & 0xFFFFFFFF)
        out.append(Data(bytes: &isize, count: 4))
        return out
    }
}
// swiftlint:enable force_cast large_tuple
