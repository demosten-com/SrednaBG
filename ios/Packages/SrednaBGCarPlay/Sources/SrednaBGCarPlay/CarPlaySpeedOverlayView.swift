// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — ios / SrednaBGCarPlay

#if canImport(UIKit)
import UIKit
import SrednaBGCore
import SrednaBGMapCore

/// Speed HUD drawn on top of `MLNMapView` inside the CarPlay window.
/// Mirrors Android's `SpeedOverlay.kt` layout; text size floors come from
/// memory `feedback_aa_overlay_legibility.md` — hero ≥96px, label ≥36px.
@MainActor
final class CarPlaySpeedOverlayView: UIView {

    private let backgroundView = UIVisualEffectView(effect: UIBlurEffect(style: .systemUltraThinMaterialDark))

    private let heroSpeedLabel = UILabel()
    private let heroSubtitleLabel = UILabel()
    private let smallSpeedLabel = UILabel()
    private let smallSubtitleLabel = UILabel()
    private let limitContainer = UIView()
    private let limitLabel = UILabel()
    private let distanceLabel = UILabel()
    private let distanceSubtitleLabel = UILabel()
    private let statusLabel = UILabel()

    private var model: CarPlaySpeedOverlayModel?

    override init(frame: CGRect) {
        super.init(frame: frame)
        configureHierarchy()
    }

    required init?(coder: NSCoder) {
        super.init(coder: coder)
        configureHierarchy()
    }

    func apply(_ model: CarPlaySpeedOverlayModel) {
        guard self.model != model else { return }
        self.model = model

        heroSpeedLabel.text = model.heroSpeedText
        heroSubtitleLabel.text = model.heroSubtitle.uppercased()
        smallSpeedLabel.text = model.smallSpeedText
        smallSubtitleLabel.text = model.smallSubtitle?.uppercased()
        limitLabel.text = model.limitText
        distanceLabel.text = model.distanceText
        distanceSubtitleLabel.text = model.distanceSubtitle?.uppercased()
        statusLabel.text = model.statusLabel

        let hasSmall = model.smallSpeedText != nil
        smallSpeedLabel.isHidden = !hasSmall
        smallSubtitleLabel.isHidden = !hasSmall

        let hasLimit = model.limitText != nil
        limitContainer.isHidden = !hasLimit

        let hasDistance = model.distanceText != nil
        distanceLabel.isHidden = !hasDistance
        distanceSubtitleLabel.isHidden = !hasDistance

        let statusColor: UIColor = (model.packedStatusColor == 0) ? .white : statusUIColor(model.packedStatusColor)
        heroSpeedLabel.textColor = statusColor
        statusLabel.textColor = statusColor
        limitContainer.layer.borderColor = UIColor.systemRed.cgColor
    }

    private func configureHierarchy() {
        translatesAutoresizingMaskIntoConstraints = false
        layer.cornerRadius = 20
        clipsToBounds = true

        backgroundView.translatesAutoresizingMaskIntoConstraints = false
        addSubview(backgroundView)

        heroSpeedLabel.font = .monospacedDigitSystemFont(ofSize: 96, weight: .bold)
        heroSpeedLabel.textColor = .white
        heroSpeedLabel.adjustsFontSizeToFitWidth = true
        heroSpeedLabel.minimumScaleFactor = 0.6
        heroSpeedLabel.textAlignment = .center

        heroSubtitleLabel.font = .systemFont(ofSize: 20, weight: .semibold)
        heroSubtitleLabel.textColor = UIColor.white.withAlphaComponent(0.7)
        heroSubtitleLabel.textAlignment = .center
        heroSubtitleLabel.setContentHuggingPriority(.required, for: .vertical)

        smallSpeedLabel.font = .monospacedDigitSystemFont(ofSize: 48, weight: .semibold)
        smallSpeedLabel.textColor = .white
        smallSpeedLabel.textAlignment = .center

        smallSubtitleLabel.font = .systemFont(ofSize: 18, weight: .medium)
        smallSubtitleLabel.textColor = UIColor.white.withAlphaComponent(0.7)
        smallSubtitleLabel.textAlignment = .center

        limitContainer.translatesAutoresizingMaskIntoConstraints = false
        limitContainer.backgroundColor = .white
        limitContainer.layer.borderColor = UIColor.systemRed.cgColor
        limitContainer.layer.borderWidth = 5
        limitLabel.translatesAutoresizingMaskIntoConstraints = false
        limitLabel.font = .monospacedDigitSystemFont(ofSize: 40, weight: .heavy)
        limitLabel.textColor = .black
        limitLabel.textAlignment = .center
        limitContainer.addSubview(limitLabel)

        distanceLabel.font = .monospacedDigitSystemFont(ofSize: 36, weight: .semibold)
        distanceLabel.textColor = .white
        distanceLabel.textAlignment = .center

        distanceSubtitleLabel.font = .systemFont(ofSize: 18, weight: .medium)
        distanceSubtitleLabel.textColor = UIColor.white.withAlphaComponent(0.7)
        distanceSubtitleLabel.textAlignment = .center

        statusLabel.font = .systemFont(ofSize: 22, weight: .semibold)
        statusLabel.textColor = .white
        statusLabel.textAlignment = .center
        statusLabel.numberOfLines = 2

        let heroStack = UIStackView(arrangedSubviews: [heroSpeedLabel, heroSubtitleLabel])
        heroStack.axis = .vertical
        heroStack.alignment = .center
        heroStack.spacing = 2

        let smallStack = UIStackView(arrangedSubviews: [smallSpeedLabel, smallSubtitleLabel])
        smallStack.axis = .vertical
        smallStack.alignment = .center
        smallStack.spacing = 2

        let distanceStack = UIStackView(arrangedSubviews: [distanceLabel, distanceSubtitleLabel])
        distanceStack.axis = .vertical
        distanceStack.alignment = .center
        distanceStack.spacing = 2

        let rowStack = UIStackView(arrangedSubviews: [heroStack, smallStack, limitContainer, distanceStack])
        rowStack.axis = .horizontal
        rowStack.alignment = .center
        rowStack.distribution = .equalCentering
        rowStack.spacing = 24
        rowStack.translatesAutoresizingMaskIntoConstraints = false

        let vStack = UIStackView(arrangedSubviews: [rowStack, statusLabel])
        vStack.axis = .vertical
        vStack.alignment = .fill
        vStack.spacing = 8
        vStack.translatesAutoresizingMaskIntoConstraints = false
        addSubview(vStack)

        NSLayoutConstraint.activate([
            backgroundView.topAnchor.constraint(equalTo: topAnchor),
            backgroundView.bottomAnchor.constraint(equalTo: bottomAnchor),
            backgroundView.leadingAnchor.constraint(equalTo: leadingAnchor),
            backgroundView.trailingAnchor.constraint(equalTo: trailingAnchor),

            vStack.topAnchor.constraint(equalTo: topAnchor, constant: 16),
            vStack.bottomAnchor.constraint(equalTo: bottomAnchor, constant: -12),
            vStack.leadingAnchor.constraint(equalTo: leadingAnchor, constant: 20),
            vStack.trailingAnchor.constraint(equalTo: trailingAnchor, constant: -20),

            heroSpeedLabel.widthAnchor.constraint(greaterThanOrEqualToConstant: 140),

            limitContainer.widthAnchor.constraint(equalToConstant: 72),
            limitContainer.heightAnchor.constraint(equalToConstant: 72),
            limitLabel.centerXAnchor.constraint(equalTo: limitContainer.centerXAnchor),
            limitLabel.centerYAnchor.constraint(equalTo: limitContainer.centerYAnchor)
        ])
    }

    override func layoutSubviews() {
        super.layoutSubviews()
        // Update to perfect circle; border width already set.
        limitContainer.layer.cornerRadius = limitContainer.bounds.width / 2
    }
}
#endif
