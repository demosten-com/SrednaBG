// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — ios / SrednaBGMapCore

import Foundation
import SQLite3

/// Read-only actor around the `sqlite3` C API. Serves vector tiles for
/// `LocalTileServer`. MBTiles stores tiles in TMS Y-order; MapLibre
/// requests XYZ Y by default — `tile(z:x:y:)` takes XYZ Y and inverts
/// internally.
///
/// The actor serializes reads; combined with `SQLITE_OPEN_FULLMUTEX`
/// this is safe to share across the listener's dispatch queue.
public actor MBTilesReader {

    public enum ReaderError: Error, CustomStringConvertible {
        case openFailed(code: Int32, message: String)
        case prepareFailed(code: Int32, message: String)

        public var description: String {
            switch self {
            case .openFailed(let code, let msg):
                return "MBTilesReader open failed (code \(code)): \(msg)"
            case .prepareFailed(let code, let msg):
                return "MBTilesReader prepare failed (code \(code)): \(msg)"
            }
        }
    }

    // `nonisolated(unsafe)` because the underlying sqlite handles are
    // thread-safe to close from any thread (we opened with
    // `SQLITE_OPEN_FULLMUTEX`) and Swift 6 would otherwise block
    // nonisolated `deinit` from touching actor state.
    private nonisolated(unsafe) var db: OpaquePointer?
    private nonisolated(unsafe) var tileStmt: OpaquePointer?
    private nonisolated(unsafe) var metaStmt: OpaquePointer?

    public let path: String

    public init(path: String) throws {
        self.path = path
        let flags = SQLITE_OPEN_READONLY | SQLITE_OPEN_FULLMUTEX
        var handle: OpaquePointer?
        let open = sqlite3_open_v2(path, &handle, flags, nil)
        guard open == SQLITE_OK, let handle else {
            let msg = handle.map { String(cString: sqlite3_errmsg($0)) } ?? "open failed"
            if let handle { sqlite3_close_v2(handle) }
            throw ReaderError.openFailed(code: open, message: msg)
        }
        self.db = handle

        let tileSQL = "SELECT tile_data FROM tiles WHERE zoom_level=?1 AND tile_column=?2 AND tile_row=?3 LIMIT 1"
        var tileStmt: OpaquePointer?
        let tilePrep = sqlite3_prepare_v2(handle, tileSQL, -1, &tileStmt, nil)
        guard tilePrep == SQLITE_OK, let tileStmt else {
            let msg = String(cString: sqlite3_errmsg(handle))
            sqlite3_close_v2(handle)
            throw ReaderError.prepareFailed(code: tilePrep, message: msg)
        }
        self.tileStmt = tileStmt

        let metaSQL = "SELECT value FROM metadata WHERE name=?1 LIMIT 1"
        var metaStmt: OpaquePointer?
        // `metadata` table is optional in MBTiles spec; prepare is best-effort.
        if sqlite3_prepare_v2(handle, metaSQL, -1, &metaStmt, nil) == SQLITE_OK {
            self.metaStmt = metaStmt
        }
    }

    deinit {
        if let tileStmt { sqlite3_finalize(tileStmt) }
        if let metaStmt { sqlite3_finalize(metaStmt) }
        if let db { sqlite3_close_v2(db) }
    }

    /// Returns the raw `tile_data` blob for the requested XYZ tile, or nil
    /// if not present. Caller must not assume any compression; sniff the
    /// first two bytes for `0x1f 0x8b` (gzip magic) if it matters.
    public func tile(z: Int, x: Int, y: Int) -> Data? {
        guard let stmt = tileStmt else { return nil }
        let tmsY = (1 << z) - 1 - y
        sqlite3_reset(stmt)
        sqlite3_clear_bindings(stmt)
        sqlite3_bind_int(stmt, 1, Int32(z))
        sqlite3_bind_int(stmt, 2, Int32(x))
        sqlite3_bind_int(stmt, 3, Int32(tmsY))
        let step = sqlite3_step(stmt)
        guard step == SQLITE_ROW else { return nil }
        guard let bytes = sqlite3_column_blob(stmt, 0) else { return nil }
        let len = Int(sqlite3_column_bytes(stmt, 0))
        return Data(bytes: bytes, count: len)
    }

    public func metadata(_ key: String) -> String? {
        guard let stmt = metaStmt else { return nil }
        sqlite3_reset(stmt)
        sqlite3_clear_bindings(stmt)
        // SQLITE_TRANSIENT — SQLite must copy the bound string before we
        // release the Swift String's storage when this scope exits.
        let transient = unsafeBitCast(-1, to: sqlite3_destructor_type.self)
        _ = key.withCString { cstr in
            sqlite3_bind_text(stmt, 1, cstr, -1, transient)
        }
        let step = sqlite3_step(stmt)
        guard step == SQLITE_ROW else { return nil }
        guard let cstr = sqlite3_column_text(stmt, 0) else { return nil }
        return String(cString: cstr)
    }
}
