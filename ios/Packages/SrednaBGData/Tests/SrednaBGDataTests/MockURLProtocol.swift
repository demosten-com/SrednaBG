// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — ios / SrednaBGData

// `URLProtocol.canInit(with:)` and `canonicalRequest(for:)` are declared
// as `class func` on the superclass, so overrides have to match — `static`
// is not an option here.
// swiftlint:disable static_over_final_class
import Foundation

/// `URLProtocol` subclass that routes every `URLRequest` made through a
/// `URLSession` configured with `MockURLProtocol.self` to a static handler.
///
/// Strict-concurrency note: handlers run on the URL loading thread, not the
/// test actor. Stash request expectations behind the lock and read them back
/// after the awaited `data(from:)` returns.
final class MockURLProtocol: URLProtocol, @unchecked Sendable {
    typealias Handler = @Sendable (URLRequest) throws -> (HTTPURLResponse, Data)

    private static let lock = NSLock()
    nonisolated(unsafe) private static var _handler: Handler?

    static func setHandler(_ handler: Handler?) {
        lock.lock(); defer { lock.unlock() }
        _handler = handler
    }

    static func currentHandler() -> Handler? {
        lock.lock(); defer { lock.unlock() }
        return _handler
    }

    /// Convenience: returns a `URLSession` with the mock protocol installed.
    static func makeSession() -> URLSession {
        let config = URLSessionConfiguration.ephemeral
        config.protocolClasses = [MockURLProtocol.self]
        return URLSession(configuration: config)
    }

    override class func canInit(with request: URLRequest) -> Bool { true }

    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

    override func startLoading() {
        guard let handler = MockURLProtocol.currentHandler() else {
            client?.urlProtocol(self, didFailWithError: URLError(.badServerResponse))
            return
        }
        do {
            let (response, data) = try handler(request)
            client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
            client?.urlProtocol(self, didLoad: data)
            client?.urlProtocolDidFinishLoading(self)
        } catch {
            client?.urlProtocol(self, didFailWithError: error)
        }
    }

    override func stopLoading() {}
}

extension HTTPURLResponse {
    static func ok(_ url: URL, contentType: String = "application/json") -> HTTPURLResponse {
        HTTPURLResponse(
            url: url,
            statusCode: 200,
            httpVersion: "HTTP/1.1",
            headerFields: ["Content-Type": contentType]
        )!
    }

    static func status(_ code: Int, _ url: URL) -> HTTPURLResponse {
        HTTPURLResponse(
            url: url,
            statusCode: code,
            httpVersion: "HTTP/1.1",
            headerFields: nil
        )!
    }
}
// swiftlint:enable static_over_final_class
