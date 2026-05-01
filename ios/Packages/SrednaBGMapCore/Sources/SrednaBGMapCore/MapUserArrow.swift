// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — ios / SrednaBGMapCore

#if canImport(UIKit)
import UIKit

/// Renders the user-location arrow as a real RGBA bitmap (via
/// `UIGraphicsImageRenderer`) so the colors survive MapLibre's sprite-atlas
/// extraction. Geometry + colors mirror Android's
/// `res/drawable/ic_nav_arrow.xml` 1:1 — `#1976D2` fill with a `#FFFFFF`
/// stroke, drawn from the same `M12,2 L19,20 L12,16 L5,20 Z` path in a
/// 24-unit viewport — so the arrow reads cleanly on both light and dark map
/// themes.
public enum MapUserArrow {

    public static let imageName = "user-arrow"

    public static func makeImage(pointSize: CGFloat = 42) -> UIImage {
        let viewport: CGFloat = 24
        let strokeInPath: CGFloat = 1.5
        let scale = pointSize / viewport
        let strokeInOutput = strokeInPath * scale
        let canvasSize = CGSize(
            width: pointSize + strokeInOutput,
            height: pointSize + strokeInOutput
        )

        let renderer = UIGraphicsImageRenderer(size: canvasSize)
        return renderer.image { ctx in
            let cg = ctx.cgContext
            cg.translateBy(x: strokeInOutput / 2, y: strokeInOutput / 2)
            cg.scaleBy(x: scale, y: scale)

            let path = UIBezierPath()
            path.move(to: CGPoint(x: 12, y: 2))
            path.addLine(to: CGPoint(x: 19, y: 20))
            path.addLine(to: CGPoint(x: 12, y: 16))
            path.addLine(to: CGPoint(x: 5, y: 20))
            path.close()
            path.lineJoinStyle = .round
            path.lineWidth = strokeInPath

            UIColor(red: 0x19 / 255, green: 0x76 / 255, blue: 0xD2 / 255, alpha: 1).setFill()
            UIColor.white.setStroke()
            path.fill()
            path.stroke()
        }
    }
}
#endif
