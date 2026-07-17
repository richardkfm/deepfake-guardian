---
layer_id: api
display_name: Generic HTTP API (bring your own model)
provider: api
enabled: false
weight: 1.0
order: 60
---

## Description
Sends face crops to a user-configured HTTP endpoint (`DEEPFAKE_API_URL`) for
deepfake analysis. Useful for self-hosted models or alternative cloud
services; the score is extracted from the JSON response via
`DEEPFAKE_API_SCORE_PATH` (dot-separated path, default `score`).

GDPR notice: face image data is sent to whatever endpoint you configure —
review that service's own data-processing terms before enabling.
