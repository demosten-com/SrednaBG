// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — ios / SrednaBGMapCore

// Labelled 4-tuples of tile coordinates (z/x/tmsY/data) read cleaner
// than a struct for these fixtures.
// swiftlint:disable large_tuple
import Foundation
import SQLite3
import Testing
@testable import SrednaBGMapCore

@Suite("MBTilesReader")
struct MBTilesReaderTests {

    @Test("returnsTileDataForXYZWithTMSYFlip")
    func returnsTileDataForXYZWithTMSYFlip() async throws {
        let dir = try makeTempDir()
        let path = dir.appendingPathComponent("fixture.mbtiles").path
        let payload = Data([0x1F, 0x8B, 0x08, 0xDE, 0xAD, 0xBE, 0xEF])
        // Insert at TMS y=0 (z=1 has TMS rows 0..1; XYZ y=1 inverts to TMS 0).
        try writeFixture(path: path, tiles: [(z: 1, x: 0, tmsY: 0, data: payload)], metadata: [:])

        let reader = try MBTilesReader(path: path)
        let bytes = await reader.tile(z: 1, x: 0, y: 1)
        #expect(bytes == payload)

        let missing = await reader.tile(z: 1, x: 0, y: 0)   // TMS y=1, not inserted
        #expect(missing == nil)
    }

    @Test("returnsNilForMissingTile")
    func returnsNilForMissingTile() async throws {
        let dir = try makeTempDir()
        let path = dir.appendingPathComponent("fixture.mbtiles").path
        try writeFixture(path: path, tiles: [], metadata: [:])

        let reader = try MBTilesReader(path: path)
        let bytes = await reader.tile(z: 99, x: 0, y: 0)
        #expect(bytes == nil)
    }

    @Test("roundTripsMetadata")
    func roundTripsMetadata() async throws {
        let dir = try makeTempDir()
        let path = dir.appendingPathComponent("fixture.mbtiles").path
        try writeFixture(
            path: path,
            tiles: [],
            metadata: ["minzoom": "5", "maxzoom": "12", "name": "srednabg"]
        )

        let reader = try MBTilesReader(path: path)
        let minz = await reader.metadata("minzoom")
        let maxz = await reader.metadata("maxzoom")
        let name = await reader.metadata("name")
        let missing = await reader.metadata("not-a-key")

        #expect(minz == "5")
        #expect(maxz == "12")
        #expect(name == "srednabg")
        #expect(missing == nil)
    }

    @Test("openFailsOnMissingFile")
    func openFailsOnMissingFile() {
        #expect(throws: MBTilesReader.ReaderError.self) {
            _ = try MBTilesReader(path: "/no/such/file.mbtiles")
        }
    }

    // MARK: - Fixture helpers

    private func makeTempDir() throws -> URL {
        let dir = FileManager.default.temporaryDirectory
            .appendingPathComponent("mbtiles-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        return dir
    }

    private func writeFixture(
        path: String,
        tiles: [(z: Int, x: Int, tmsY: Int, data: Data)],
        metadata: [String: String]
    ) throws {
        var handle: OpaquePointer?
        let open = sqlite3_open_v2(path, &handle, SQLITE_OPEN_CREATE | SQLITE_OPEN_READWRITE, nil)
        guard open == SQLITE_OK, let handle else {
            throw FixtureError.sqliteFailed(open)
        }
        defer { sqlite3_close_v2(handle) }

        try exec(handle, "CREATE TABLE tiles(zoom_level INTEGER, tile_column INTEGER, tile_row INTEGER, tile_data BLOB);")
        try exec(handle, "CREATE TABLE metadata(name TEXT, value TEXT);")

        for tile in tiles {
            var stmt: OpaquePointer?
            try checked(sqlite3_prepare_v2(
                handle,
                "INSERT INTO tiles(zoom_level,tile_column,tile_row,tile_data) VALUES (?,?,?,?)",
                -1, &stmt, nil
            ))
            sqlite3_bind_int(stmt, 1, Int32(tile.z))
            sqlite3_bind_int(stmt, 2, Int32(tile.x))
            sqlite3_bind_int(stmt, 3, Int32(tile.tmsY))
            tile.data.withUnsafeBytes { raw in
                let transient = unsafeBitCast(-1, to: sqlite3_destructor_type.self)
                _ = sqlite3_bind_blob(stmt, 4, raw.baseAddress, Int32(tile.data.count), transient)
            }
            try checked(sqlite3_step(stmt), expected: SQLITE_DONE)
            sqlite3_finalize(stmt)
        }

        for (k, v) in metadata {
            var stmt: OpaquePointer?
            try checked(sqlite3_prepare_v2(
                handle,
                "INSERT INTO metadata(name,value) VALUES (?,?)",
                -1, &stmt, nil
            ))
            let transient = unsafeBitCast(-1, to: sqlite3_destructor_type.self)
            _ = k.withCString { sqlite3_bind_text(stmt, 1, $0, -1, transient) }
            _ = v.withCString { sqlite3_bind_text(stmt, 2, $0, -1, transient) }
            try checked(sqlite3_step(stmt), expected: SQLITE_DONE)
            sqlite3_finalize(stmt)
        }
    }

    private func exec(_ db: OpaquePointer, _ sql: String) throws {
        var err: UnsafeMutablePointer<CChar>?
        let rc = sqlite3_exec(db, sql, nil, nil, &err)
        if rc != SQLITE_OK {
            let msg = err.map { String(cString: $0) } ?? "sqlite3_exec failed"
            sqlite3_free(err)
            throw FixtureError.execFailed(code: rc, message: msg)
        }
    }

    private func checked(_ rc: Int32, expected: Int32 = SQLITE_OK) throws {
        if rc != expected {
            throw FixtureError.sqliteFailed(rc)
        }
    }

    enum FixtureError: Error {
        case sqliteFailed(Int32)
        case execFailed(code: Int32, message: String)
    }
}
// swiftlint:enable large_tuple
