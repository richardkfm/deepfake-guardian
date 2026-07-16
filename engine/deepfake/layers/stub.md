---
layer_id: stub
display_name: Stub (safe placeholder)
provider: stub
enabled: true
weight: 1.0
order: 10
---

## Description
Fixed low-score placeholder detector (0.05) — always available, makes no
external calls. Ships enabled by default so a `DEEPFAKE_LAYERS` deployment
has a working detector out of the box, mirroring the `DEEPFAKE_PROVIDER=stub`
default.
