// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — ios / SrednaBGData

import Foundation
import Network

/// Loopback HTTP/1.1 debug listener for the QA harness.
///
/// Replaces the `srednabg-debug://` URL scheme: `simctl openurl` triggers an
/// "Open in SrednaBG" confirmation dialog on every dispatch, which makes
/// automated runs unusable. The iOS Simulator shares the host's loopback,
/// so the harness on macOS can reach `127.0.0.1:<port>` directly with no
/// system prompt and a synchronous status code.
///
/// Endpoints (all `GET`, ignore body):
///   - `/setting?key=K&value=V`
///   - `/sync?action=zones|map`
///   - `/tracking?action=start|stop`
///   - `/mute?on=1|0`
///   - `/network?offline=1|0`
///   - `/ping` — liveness check, used by `IosDevice.require_device()`
///
/// Bound to `127.0.0.1` only; never reachable off-device. Started by
/// `SrednaBGApp.init()` under `#if DEBUG` and never started in release.
public final class DebugControlServer: @unchecked Sendable {

    public static let defaultPort: UInt16 = 47823

    public enum ServerError: Error, CustomStringConvertible {
        case notReady
        case listenerFailed(NWError)
        public var description: String {
            switch self {
            case .notReady: return "DebugControlServer not ready"
            case .listenerFailed(let e): return "NWListener failed: \(e)"
            }
        }
    }

    private let router: DebugActionRouter
    private let port: UInt16
    private let queue = DispatchQueue(label: "bg.srednabg.DebugControlServer", qos: .userInitiated)
    private var listener: NWListener?

    public init(router: DebugActionRouter, port: UInt16 = DebugControlServer.defaultPort) {
        self.router = router
        self.port = port
    }

    public func start() async throws {
        if listener != nil { return }

        let tcpOptions = NWProtocolTCP.Options()
        let parameters = NWParameters(tls: nil, tcp: tcpOptions)
        parameters.allowLocalEndpointReuse = true
        // Bind to a fixed port. Don't set `requiredLocalEndpoint` —
        // combining it with the `on:` argument silently prevents the
        // listener from reaching `.ready` on the iOS Simulator.
        guard let nwPort = NWEndpoint.Port(rawValue: port) else {
            throw ServerError.notReady
        }

        let newListener: NWListener
        do {
            newListener = try NWListener(using: parameters, on: nwPort)
        } catch {
            QALog.location.error("DebugControlServer init failed: \(String(describing: error), privacy: .public)")
            throw error
        }
        self.listener = newListener

        try await withCheckedThrowingContinuation { (cont: CheckedContinuation<Void, Error>) in
            let doneBox = OneShot()
            newListener.stateUpdateHandler = { [weak self] state in
                guard let self else { return }
                switch state {
                case .ready:
                    QALog.location.info("DebugControlServer ready on port \(self.port, privacy: .public)")
                    if doneBox.finish() { cont.resume() }
                case .failed(let error):
                    QALog.location.error("DebugControlServer failed: \(String(describing: error), privacy: .public)")
                    if doneBox.finish() { cont.resume(throwing: ServerError.listenerFailed(error)) }
                case .cancelled:
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
    }

    private func accept(connection: NWConnection) {
        connection.start(queue: queue)
        receive(connection: connection, buffer: Data())
    }

    private func receive(connection: NWConnection, buffer: Data) {
        connection.receive(minimumIncompleteLength: 1, maximumLength: 4096) { [weak self] data, _, isComplete, error in
            guard let self else { return }
            var acc = buffer
            if let data = data, !data.isEmpty {
                acc.append(data)
            }
            // HTTP/1.1 request: parse once we see the end-of-headers CRLF CRLF.
            if let endOfHeaders = self.indexOfDoubleCRLF(in: acc) {
                let head = acc[..<endOfHeaders]
                self.handleRequest(head: head, connection: connection)
                return
            }
            if isComplete || error != nil {
                connection.cancel()
                return
            }
            self.receive(connection: connection, buffer: acc)
        }
    }

    private func handleRequest(head: Data, connection: NWConnection) {
        guard let text = String(data: head, encoding: .utf8) else {
            respond(connection: connection, status: 400, body: "bad request")
            return
        }
        // First line: `GET /path?query HTTP/1.1\r\n…`
        let firstLineEnd = text.firstIndex(of: "\r") ?? text.endIndex
        let firstLine = text[..<firstLineEnd]
        let parts = firstLine.split(separator: " ", maxSplits: 2, omittingEmptySubsequences: false)
        guard parts.count >= 2 else {
            respond(connection: connection, status: 400, body: "bad request line")
            return
        }
        let target = String(parts[1])
        let (path, params) = parsePathAndQuery(target)

        // Hop to MainActor for the action; respond on the connection's queue.
        Task { @MainActor [router] in
            let result = await router.dispatch(path: path, params: params)
            self.respond(connection: connection, status: result.status, body: result.body)
        }
    }

    private func parsePathAndQuery(_ target: String) -> (String, [String: String]) {
        let comps = target.split(separator: "?", maxSplits: 1, omittingEmptySubsequences: false)
        let path = String(comps[0])
        var params: [String: String] = [:]
        if comps.count == 2 {
            for pair in comps[1].split(separator: "&") {
                let kv = pair.split(separator: "=", maxSplits: 1, omittingEmptySubsequences: false)
                let key = String(kv[0]).removingPercentEncoding ?? String(kv[0])
                let value = kv.count == 2 ? (String(kv[1]).removingPercentEncoding ?? String(kv[1])) : ""
                params[key] = value
            }
        }
        return (path, params)
    }

    private func respond(connection: NWConnection, status: Int, body: String) {
        let phrase = status == 200 ? "OK" : (status == 400 ? "Bad Request" : "Error")
        let bodyData = Data(body.utf8)
        var response = "HTTP/1.1 \(status) \(phrase)\r\n"
        response += "Content-Type: text/plain; charset=utf-8\r\n"
        response += "Content-Length: \(bodyData.count)\r\n"
        response += "Connection: close\r\n\r\n"
        var data = Data(response.utf8)
        data.append(bodyData)
        connection.send(content: data, completion: .contentProcessed { _ in
            connection.cancel()
        })
    }

    private func indexOfDoubleCRLF(in data: Data) -> Data.Index? {
        let crlf2: [UInt8] = [0x0D, 0x0A, 0x0D, 0x0A]
        guard data.count >= crlf2.count else { return nil }
        var i = data.startIndex
        while i <= data.endIndex - crlf2.count {
            if data[i] == crlf2[0] && data[i + 1] == crlf2[1]
                && data[i + 2] == crlf2[2] && data[i + 3] == crlf2[3] {
                return data.index(i, offsetBy: crlf2.count)
            }
            i = data.index(after: i)
        }
        return nil
    }
}

/// Tiny once-only guard for continuations — `NWListener` can emit both
/// `.ready` and `.failed` in rare orderings; the continuation must resume
/// exactly once.
private final class OneShot: @unchecked Sendable {
    private var done = false
    private let lock = NSLock()
    func finish() -> Bool {
        lock.lock(); defer { lock.unlock() }
        if done { return false }
        done = true
        return true
    }
}
