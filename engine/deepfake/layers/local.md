---
layer_id: local
display_name: Local ONNX model (on-device)
provider: local
enabled: false
weight: 1.0
order: 40
---

## Description
Runs a locally-hosted EfficientNet-B0 model (trained on FaceForensics++) via
ONNX Runtime. The only fully on-device provider — no network calls, no
third-party data sharing. Model path is configured via `DEEPFAKE_MODEL_PATH`
(defaults to `~/.cache/deepfake_guardian/efficientnet_b0_deepfake.onnx`).
