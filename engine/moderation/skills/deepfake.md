---
category_id: deepfake_suspect
display_name: Deepfake Suspect
core: true
order: 40
modalities: [image, video]
thresholds: { minors_strict: 0.6, default: 0.7, permissive: 0.9 }
flag_threshold: 0.4
---

## Description
Manipulated or AI-generated (deepfake) faces in images or video. Detection is
performed by the provider-based pipeline in `engine/deepfake/`; this file holds
its thresholds and user-facing messages.

The detection *backends* actually run are configured via
`engine/deepfake/layers/*.md` and the `DEEPFAKE_LAYERS` env var (see
CLAUDE.md § Deepfake Detection Layers) — this file continues to hold only
thresholds and messages for the `deepfake_suspect` category, not detection
logic.

When a deepfaked face also carries a strong sexual-content signal, the
combined harm — non-consensual intimate imagery / "revenge porn" — is scored
under the `sexual_violence` category instead (see `sexual_violence.md`), so
it can be evaluated against that category's (typically stricter) threshold.

## Educational message (en)
This media may be a manipulated or AI-generated (deepfake) image or video.

## Educational message (de)
Dieses Medium könnte ein manipuliertes oder KI-generiertes (Deepfake-)Bild oder -Video sein.
