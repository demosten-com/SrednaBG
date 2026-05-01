// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — ios / SrednaBGMapCore

import Foundation
import Network
import Compression

/// Minimal loopback HTTP/1.1 server that translates MapLibre's
/// `http://127.0.0.1:<port>/tiles/{z}/{x}/{y}.pbf` requests into
/// `MBTilesReader` lookups. Binds to `127.0.0.1` only — never reachable
/// off-device. Ephemeral port; the template is read back after `start()`.
///
/// Threading: accept/recv/send run on a dedicated serial dispatch queue
/// owned by the `NWListener`. SQLite reads delegate to the actor-isolated
/// `MBTilesReader`. State on this class is guarded by an internal actor.
public final class LocalTileServer: @unchecked Sendable {

    public enum ServerError: Error, CustomStringConvertible {
        case notReady
        case listenerFailed(NWError)

        public var description: String {
            switch self {
            case .notReady: return "LocalTileServer not ready"
            case .listenerFailed(let e): return "NWListener failed: \(e)"
            }
        }
    }

    public let reader: MBTilesReader

    private let queue = DispatchQueue(label: "bg.srednabg.LocalTileServer", qos: .userInitiated)
    private var listener: NWListener?
    private var activeConnections: Set<ObjectIdentifier> = []
    private var closedConnections: Set<ObjectIdentifier> = []
    private var connectionsLock = NSLock()

    private var readyURL: URL?

    public init(reader: MBTilesReader) {
        self.reader = reader
    }

    /// Bind and return the base URL (e.g. `http://127.0.0.1:54321`). Throws
    /// if the listener never reaches `.ready`.
    public func start() async throws -> URL {
        if let readyURL { return readyURL }

        let tcpOptions = NWProtocolTCP.Options()
        let parameters = NWParameters(tls: nil, tcp: tcpOptions)
        parameters.requiredLocalEndpoint = NWEndpoint.hostPort(host: "127.0.0.1", port: .any)
        parameters.allowLocalEndpointReuse = true

        let newListener = try NWListener(using: parameters)
        self.listener = newListener

        let url: URL = try await withCheckedThrowingContinuation { (cont: CheckedContinuation<URL, Error>) in
            // Continuation must be resumed exactly once. `done` guards against
            // the rare case where both `.ready` and `.failed` fire in quick
            // succession (seen on iOS when a sibling listener crashed out).
            let doneBox = ContinuationBox()

            newListener.stateUpdateHandler = { [weak self] state in
                guard let self else { return }
                switch state {
                case .ready:
                    guard let port = newListener.port else {
                        if doneBox.finish() {
                            cont.resume(throwing: ServerError.notReady)
                        }
                        return
                    }
                    let u = URL(string: "http://127.0.0.1:\(port.rawValue)")!
                    self.readyURL = u
                    if doneBox.finish() { cont.resume(returning: u) }
                case .failed(let error):
                    if doneBox.finish() { cont.resume(throwing: ServerError.listenerFailed(error)) }
                case .cancelled:
                    // Only an error during startup — post-start cancel is `stop()`.
                    if doneBox.finish() { cont.resume(throwing: ServerError.notReady) }
                default:
                    break
                }
            }

            newListener.newConnectionHandler = { [weak self] connection in
                self?.accept(connection: connection)
            }

            newListener.start(queue: queue)
        }

        return url
    }

    public func stop() async {
        await withCheckedContinuation { (cont: CheckedContinuation<Void, Never>) in
            queue.async {
                self.listener?.cancel()
                self.listener = nil
                self.readyURL = nil
                cont.resume()
            }
        }
    }

    public var tileURLTemplate: String? {
        // Build manually — `URL.appendingPathComponent` percent-encodes the
        // braces into `%7B..%7D` and MapLibre needs the literal placeholders.
        guard let url = readyURL else { return nil }
        return url.absoluteString + "/tiles/{z}/{x}/{y}.pbf"
    }

    // MARK: - Connection handling

    private func accept(connection: NWConnection) {
        let id = ObjectIdentifier(connection)
        connectionsLock.lock()
        activeConnections.insert(id)
        connectionsLock.unlock()

        connection.stateUpdateHandler = { [weak self] state in
            switch state {
            case .ready:
                self?.receiveRequest(on: connection, buffer: Data(), id: id)
            case .failed, .cancelled:
                self?.close(connection: connection, id: id)
            default:
                break
            }
        }
        connection.start(queue: queue)
    }

    private func close(connection: NWConnection, id: ObjectIdentifier) {
        // `stateUpdateHandler` fires `.cancelled` in response to our own
        // `cancel()` call, which would otherwise re-enter this method and
        // log "is already cancelled, ignoring cancel" to the console.
        // Deduplicate by ObjectIdentifier so we cancel each connection once.
        connectionsLock.lock()
        let alreadyClosed = closedConnections.contains(id)
        if !alreadyClosed { closedConnections.insert(id) }
        activeConnections.remove(id)
        connectionsLock.unlock()
        if !alreadyClosed {
            connection.cancel()
        }
    }

    private func receiveRequest(on connection: NWConnection, buffer: Data, id: ObjectIdentifier) {
        connection.receive(minimumIncompleteLength: 1, maximumLength: 4096) { [weak self] data, _, isComplete, error in
            guard let self else { return }
            if let error {
                _ = error  // swallow — close below
                self.close(connection: connection, id: id)
                return
            }
            var nextBuffer = buffer
            if let data, !data.isEmpty { nextBuffer.append(data) }

            // End-of-headers marker for HTTP/1.1.
            let terminator = Data([0x0D, 0x0A, 0x0D, 0x0A])
            if let range = nextBuffer.range(of: terminator) {
                let headerData = nextBuffer[..<range.lowerBound]
                let request = Self.parseRequest(headerData: headerData)
                Task { await self.respond(to: request, on: connection, id: id) }
                return
            }

            // 16 KB cap guards against junk clients.
            if nextBuffer.count > 16_384 {
                self.sendRaw(
                    connection: connection,
                    status: "400 Bad Request",
                    body: Data(),
                    contentType: nil,
                    contentEncoding: nil,
                    id: id
                )
                return
            }
            if isComplete {
                self.close(connection: connection, id: id)
                return
            }
            self.receiveRequest(on: connection, buffer: nextBuffer, id: id)
        }
    }

    // MARK: - HTTP parsing

    struct ParsedRequest {
        let method: String
        let path: String
    }

    static func parseRequest(headerData: Data) -> ParsedRequest? {
        guard let head = String(data: headerData, encoding: .utf8) else { return nil }
        let firstLine = head.split(separator: "\r\n", maxSplits: 1).first.map(String.init) ?? head
        let parts = firstLine.split(separator: " ", maxSplits: 2).map(String.init)
        guard parts.count >= 2 else { return nil }
        return ParsedRequest(method: parts[0], path: parts[1])
    }

    static func parseTilePath(_ path: String) -> (z: Int, x: Int, y: Int)? {
        // Strip query string + leading slash.
        let noQuery = path.split(separator: "?", maxSplits: 1).first.map(String.init) ?? path
        let trimmed = noQuery.hasPrefix("/") ? String(noQuery.dropFirst()) : noQuery
        let segments = trimmed.split(separator: "/").map(String.init)
        guard segments.count == 4, segments[0] == "tiles" else { return nil }
        guard segments[3].hasSuffix(".pbf") else { return nil }
        let yStr = String(segments[3].dropLast(4))
        guard let z = Int(segments[1]), let x = Int(segments[2]), let y = Int(yStr) else { return nil }
        return (z, x, y)
    }

    // MARK: - Responding

    private func respond(to request: ParsedRequest?, on connection: NWConnection, id: ObjectIdentifier) async {
        guard let request else {
            sendRaw(connection: connection, status: "400 Bad Request", body: Data(), contentType: nil, contentEncoding: nil, id: id)
            return
        }
        guard request.method == "GET" else {
            sendRaw(connection: connection, status: "400 Bad Request", body: Data(), contentType: nil, contentEncoding: nil, id: id)
            return
        }
        guard let coords = Self.parseTilePath(request.path) else {
            sendRaw(connection: connection, status: "400 Bad Request", body: Data(), contentType: nil, contentEncoding: nil, id: id)
            return
        }
        let data = await reader.tile(z: coords.z, x: coords.x, y: coords.y)
        guard let data, !data.isEmpty else {
            sendRaw(connection: connection, status: "204 No Content", body: Data(), contentType: nil, contentEncoding: nil, id: id)
            return
        }

        // MBTiles stores MVT payloads gzipped. MapLibre Native iOS fails
        // to paint features when we advertise `Content-Encoding: gzip`
        // (URLSession transparently decompresses, but the tile worker
        // loses the resulting MVT bytes somewhere in the HTTP file
        // source). Sending raw gzipped bytes without the header fails
        // the same way. Decompressing server-side and handing MapLibre
        // the plain MVT payload is the only combination that renders.
        let payload: Data
        if data.count >= 2 && data[data.startIndex] == 0x1F && data[data.startIndex + 1] == 0x8B {
            payload = Self.gunzip(data) ?? data
        } else {
            payload = data
        }

        sendRaw(
            connection: connection,
            status: "200 OK",
            body: payload,
            contentType: "application/x-protobuf",
            contentEncoding: nil,
            id: id
        )
    }

    /// Decompress a gzip blob (RFC 1952) using `libcompression`'s zlib algo
    /// plus the 10-byte header strip. Returns nil on malformed input.
    static func gunzip(_ gz: Data) -> Data? {
        guard gz.count > 10 else { return nil }
        let header = gz[gz.startIndex]
        let header2 = gz[gz.startIndex + 1]
        guard header == 0x1F, header2 == 0x8B else { return nil }
        // Gzip body starts 10 bytes in; trailer is last 8 bytes (CRC32 + ISIZE).
        let deflated = gz.subdata(in: (gz.startIndex + 10)..<(gz.endIndex - 8))
        // Grow output buffer iteratively — OpenMapTiles MVT expands ~3×.
        var capacity = deflated.count * 4
        for _ in 0..<6 {
            let dst = UnsafeMutablePointer<UInt8>.allocate(capacity: capacity)
            defer { dst.deallocate() }
            let written = deflated.withUnsafeBytes { (rawBuf: UnsafeRawBufferPointer) -> Int in
                guard let src = rawBuf.bindMemory(to: UInt8.self).baseAddress else { return 0 }
                return compression_decode_buffer(
                    dst, capacity,
                    src, deflated.count,
                    nil, COMPRESSION_ZLIB
                )
            }
            if written == 0 {
                return nil
            }
            if written < capacity {
                return Data(bytes: dst, count: written)
            }
            // Buffer was exactly filled — likely truncated. Grow and retry.
            capacity *= 2
        }
        return nil
    }

    private func sendRaw(
        connection: NWConnection,
        status: String,
        body: Data,
        contentType: String?,
        contentEncoding: String?,
        id: ObjectIdentifier
    ) {
        var head = "HTTP/1.1 \(status)\r\n"
        head += "Content-Length: \(body.count)\r\n"
        if let contentType { head += "Content-Type: \(contentType)\r\n" }
        if let contentEncoding { head += "Content-Encoding: \(contentEncoding)\r\n" }
        head += "Cache-Control: public, max-age=31536000, immutable\r\n"
        head += "Access-Control-Allow-Origin: *\r\n"
        head += "Connection: close\r\n"
        head += "\r\n"
        var response = Data(head.utf8)
        response.append(body)

        connection.send(content: response, completion: .contentProcessed { [weak self] _ in
            self?.close(connection: connection, id: id)
        })
    }
}

/// Thread-safe guard for resuming a continuation exactly once. We reach for
/// this because `NWListener.stateUpdateHandler` can fire `.ready` and
/// `.failed` on the same dispatch queue in rapid succession.
private final class ContinuationBox: @unchecked Sendable {
    private let lock = NSLock()
    private var isFinished = false

    /// Returns `true` if the caller should resume now; `false` if someone
    /// else already did.
    func finish() -> Bool {
        lock.lock()
        defer { lock.unlock() }
        if isFinished { return false }
        isFinished = true
        return true
    }
}
