// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — ios / SrednaBGMapCore

import Foundation

/// Rewrites a MapLibre style JSON so that `"url": "mbtiles://..."` vector
/// sources point at a loopback HTTP tile server instead. MapLibre Native
/// iOS has no `mbtiles://` scheme handler — we bridge SQLite reads through
/// `LocalTileServer`. The disk copy of the style file stays untouched
/// (byte-identical to Android, which consumes `mbtiles://` directly).
///
/// Glyphs and sprite URLs are already rewritten to `file://…` by
/// `OfflineMapInstaller`; MapLibre iOS resolves those natively.
public enum StyleRewriter {

    public enum RewriteError: Error, Equatable {
        case malformedJSON
        case notAnObject
    }

    /// Rewrite a style JSON string. Any `sources.*` dictionary whose
    /// `type == "vector"` and whose `url` begins with `mbtiles://` gets
    /// its `url` removed and a `tiles: [tileTemplate]` added. Minzoom and
    /// maxzoom are preserved if present; otherwise the defaults baked in
    /// to the rewrite are used.
    ///
    /// - Parameters:
    ///   - styleJSON: raw style JSON
    ///   - tileTemplate: e.g. `"http://127.0.0.1:54321/tiles/{z}/{x}/{y}.pbf"`
    ///   - mbtilesURI: substituted for every `{MBTILES_URI}` occurrence before
    ///     the `mbtiles:// → tiles[]` JSON pass. Pass this when the style is
    ///     kept as a raw template on disk (recommended, so absolute paths
    ///     never get baked in).
    ///   - glyphsURI: substituted for every `{GLYPHS_URI}` occurrence.
    ///   - spriteURI: substituted for every `{SPRITE_URI}` occurrence.
    ///   - defaultMinZoom: fallback when source has no explicit minzoom
    ///   - defaultMaxZoom: fallback when source has no explicit maxzoom
    public static func rewriteMbtilesToHTTP(
        styleJSON: String,
        tileTemplate: String,
        mbtilesURI: String? = nil,
        glyphsURI: String? = nil,
        spriteURI: String? = nil,
        defaultMinZoom: Int = 0,
        defaultMaxZoom: Int = 14
    ) throws -> String {
        guard let data = styleJSON.data(using: .utf8) else {
            throw RewriteError.malformedJSON
        }
        let rewritten = try rewriteMbtilesToHTTP(
            styleData: data,
            tileTemplate: tileTemplate,
            mbtilesURI: mbtilesURI,
            glyphsURI: glyphsURI,
            spriteURI: spriteURI,
            defaultMinZoom: defaultMinZoom,
            defaultMaxZoom: defaultMaxZoom
        )
        guard let out = String(data: rewritten, encoding: .utf8) else {
            throw RewriteError.malformedJSON
        }
        return out
    }

    public static func rewriteMbtilesToHTTP(
        styleData: Data,
        tileTemplate: String,
        mbtilesURI: String? = nil,
        glyphsURI: String? = nil,
        spriteURI: String? = nil,
        defaultMinZoom: Int = 0,
        defaultMaxZoom: Int = 14
    ) throws -> Data {
        // Pre-pass: swap placeholder tokens in the raw text. Must happen
        // before JSON parsing so any containing URL string is valid JSON
        // post-substitution.
        let bytes: Data
        if mbtilesURI != nil || glyphsURI != nil || spriteURI != nil {
            guard var raw = String(data: styleData, encoding: .utf8) else {
                throw RewriteError.malformedJSON
            }
            if let mbtilesURI { raw = raw.replacingOccurrences(of: "{MBTILES_URI}", with: mbtilesURI) }
            if let glyphsURI { raw = raw.replacingOccurrences(of: "{GLYPHS_URI}", with: glyphsURI) }
            if let spriteURI { raw = raw.replacingOccurrences(of: "{SPRITE_URI}", with: spriteURI) }
            guard let substituted = raw.data(using: .utf8) else {
                throw RewriteError.malformedJSON
            }
            bytes = substituted
        } else {
            bytes = styleData
        }

        let parsed: Any
        do {
            parsed = try JSONSerialization.jsonObject(with: bytes, options: [.mutableContainers])
        } catch {
            throw RewriteError.malformedJSON
        }
        guard var root = parsed as? [String: Any] else {
            throw RewriteError.notAnObject
        }

        if var sources = root["sources"] as? [String: Any] {
            for (name, raw) in sources {
                guard var source = raw as? [String: Any],
                      (source["type"] as? String) == "vector",
                      let url = source["url"] as? String,
                      url.hasPrefix("mbtiles://")
                else { continue }

                source.removeValue(forKey: "url")
                source["tiles"] = [tileTemplate]
                if source["minzoom"] == nil {
                    source["minzoom"] = defaultMinZoom
                }
                if source["maxzoom"] == nil {
                    source["maxzoom"] = defaultMaxZoom
                }
                // MapLibre uses XYZ by default; our LocalTileServer inverts
                // Y to TMS internally. Do NOT set `scheme: "tms"` here.
                sources[name] = source
            }
            root["sources"] = sources
        }

        return try JSONSerialization.data(withJSONObject: root, options: [.prettyPrinted, .sortedKeys])
    }
}
