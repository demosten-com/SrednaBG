// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — ios / SrednaBGMapCore

// Test file: `as!` unwraps on known-shape JSON fixtures are idiomatic
// in tests. Banned elsewhere via the default rule.
// swiftlint:disable force_cast
import Foundation
import Testing
@testable import SrednaBGMapCore

@Suite("StyleRewriter")
struct StyleRewriterTests {

    private static let tileTemplate = "http://127.0.0.1:54321/tiles/{z}/{x}/{y}.pbf"

    @Test("vectorMbtilesSourceIsRewrittenToTilesTemplate")
    func vectorMbtilesSourceIsRewritten() throws {
        let input = """
        {
          "version": 8,
          "sources": {
            "openmaptiles": {
              "type": "vector",
              "url": "mbtiles:///abs/path/to/bulgaria.mbtiles"
            }
          },
          "glyphs": "file:///abs/fonts/{fontstack}/{range}.pbf",
          "sprite": "file:///abs/sprite"
        }
        """

        let result = try StyleRewriter.rewriteMbtilesToHTTP(
            styleJSON: input,
            tileTemplate: Self.tileTemplate
        )
        let parsed = try JSONSerialization.jsonObject(with: Data(result.utf8)) as! [String: Any]
        let sources = parsed["sources"] as! [String: Any]
        let openmaptiles = sources["openmaptiles"] as! [String: Any]

        #expect((openmaptiles["type"] as? String) == "vector")
        #expect(openmaptiles["url"] == nil)
        #expect((openmaptiles["tiles"] as? [String]) == [Self.tileTemplate])
        #expect(openmaptiles["minzoom"] != nil)
        #expect(openmaptiles["maxzoom"] != nil)

        // Glyphs and sprite untouched (already file:// after OfflineMapInstaller).
        #expect((parsed["glyphs"] as? String) == "file:///abs/fonts/{fontstack}/{range}.pbf")
        #expect((parsed["sprite"] as? String) == "file:///abs/sprite")
    }

    @Test("nonMbtilesVectorSourcePassesThrough")
    func nonMbtilesVectorSourcePassesThrough() throws {
        let input = """
        {
          "sources": {
            "external": {
              "type": "vector",
              "url": "https://example.com/tiles.json"
            }
          }
        }
        """
        let result = try StyleRewriter.rewriteMbtilesToHTTP(
            styleJSON: input,
            tileTemplate: Self.tileTemplate
        )
        let parsed = try JSONSerialization.jsonObject(with: Data(result.utf8)) as! [String: Any]
        let sources = parsed["sources"] as! [String: Any]
        let external = sources["external"] as! [String: Any]

        #expect((external["url"] as? String) == "https://example.com/tiles.json")
        #expect(external["tiles"] == nil)
    }

    @Test("nonVectorSourceUntouched")
    func nonVectorSourceUntouched() throws {
        let input = """
        {
          "sources": {
            "raster": {
              "type": "raster",
              "url": "mbtiles:///abs/raster.mbtiles"
            }
          }
        }
        """
        let result = try StyleRewriter.rewriteMbtilesToHTTP(
            styleJSON: input,
            tileTemplate: Self.tileTemplate
        )
        let parsed = try JSONSerialization.jsonObject(with: Data(result.utf8)) as! [String: Any]
        let sources = parsed["sources"] as! [String: Any]
        let raster = sources["raster"] as! [String: Any]

        // Rewrite only fires on `type: vector`; raster URLs stay untouched.
        #expect((raster["url"] as? String) == "mbtiles:///abs/raster.mbtiles")
        #expect(raster["tiles"] == nil)
    }

    @Test("explicitZoomBoundsPreserved")
    func explicitZoomBoundsPreserved() throws {
        let input = """
        {
          "sources": {
            "v": {
              "type": "vector",
              "url": "mbtiles:///x.mbtiles",
              "minzoom": 5,
              "maxzoom": 12
            }
          }
        }
        """
        let result = try StyleRewriter.rewriteMbtilesToHTTP(
            styleJSON: input,
            tileTemplate: Self.tileTemplate
        )
        let parsed = try JSONSerialization.jsonObject(with: Data(result.utf8)) as! [String: Any]
        let v = (parsed["sources"] as! [String: Any])["v"] as! [String: Any]

        #expect((v["minzoom"] as? Int) == 5)
        #expect((v["maxzoom"] as? Int) == 12)
    }

    @Test("malformedJSONThrows")
    func malformedJSONThrows() {
        #expect(throws: StyleRewriter.RewriteError.self) {
            _ = try StyleRewriter.rewriteMbtilesToHTTP(
                styleJSON: "{not json",
                tileTemplate: Self.tileTemplate
            )
        }
    }

    @Test("topLevelArrayRejected")
    func topLevelArrayRejected() {
        #expect(throws: StyleRewriter.RewriteError.self) {
            _ = try StyleRewriter.rewriteMbtilesToHTTP(
                styleJSON: "[1, 2, 3]",
                tileTemplate: Self.tileTemplate
            )
        }
    }

    @Test("placeholderTokensSubstitutedBeforeJsonPass")
    func placeholderTokensSubstituted() throws {
        // Matches what the app ships on disk: placeholders for every absolute
        // path so nothing the container-relocation can invalidate survives to
        // MapLibre's style loader.
        let input = """
        {
          "sources": {
            "openmaptiles": {"type": "vector", "url": "{MBTILES_URI}"}
          },
          "glyphs": "{GLYPHS_URI}/{fontstack}/{range}.pbf",
          "sprite": "{SPRITE_URI}"
        }
        """
        let result = try StyleRewriter.rewriteMbtilesToHTTP(
            styleJSON: input,
            tileTemplate: Self.tileTemplate,
            mbtilesURI: "mbtiles:///fresh/path/tiles.mbtiles",
            glyphsURI: "file:///fresh/fonts",
            spriteURI: "file:///fresh/sprite"
        )
        let parsed = try JSONSerialization.jsonObject(with: Data(result.utf8)) as! [String: Any]

        #expect((parsed["glyphs"] as? String) == "file:///fresh/fonts/{fontstack}/{range}.pbf")
        #expect((parsed["sprite"] as? String) == "file:///fresh/sprite")

        // Vector source's placeholder got substituted into a real
        // `mbtiles://` URL, which the existing JSON pass then swapped for a
        // `tiles` template — the substitution and the URL rewrite must both
        // run in one call.
        let openmaptiles = (parsed["sources"] as! [String: Any])["openmaptiles"] as! [String: Any]
        #expect(openmaptiles["url"] == nil)
        #expect((openmaptiles["tiles"] as? [String]) == [Self.tileTemplate])
    }
}
// swiftlint:enable force_cast
