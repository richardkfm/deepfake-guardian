---
layer_id: sightengine
display_name: SightEngine (cloud API)
provider: sightengine
enabled: false
weight: 1.0
order: 50
---

## Description
Sends face crops to the SightEngine cloud API's `deepfake` model. Requires
`SIGHTENGINE_API_USER` and `SIGHTENGINE_API_SECRET`.

GDPR notice: face image data is sent to a third-party service. For
GDPR-sensitive deployments (especially with minors), prefer the `local`
layer, which keeps all data on-device.
