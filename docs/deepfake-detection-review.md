# Deepfake Detection — Code Review Findings

**Date:** 2026-07-04
**Scope:** `engine/deepfake/` (all providers, factory, face extractor),
`engine/classifiers.py` (`detect_deepfake_suspect`), `engine/video_processing.py`,
`engine/routes.py` (image/video endpoints), related docs and tests.

**Test status at review time:** all 68 deepfake-related unit tests pass
(`test_deepfake_factory`, `test_face_extractor`, `test_local_detector`,
`test_cloud_detector`, `test_classifiers`, `test_video_processing`). The suite
mocks the ML models, so it verifies pipeline plumbing — not detection accuracy.

---

## How the mechanism works

```
POST /moderate_image
  → MediaPipe face detection (deepfake/face_extractor.py)
  → each face crop scored by the configured provider (DEEPFAKE_PROVIDER)
  → max score across faces = deepfake_suspect
  → verdict: ≥ THRESHOLD_DEEPFAKE (0.7 default) → delete, ≥ 0.4 → flag
```

Video moderation reuses this per sampled frame (OpenCV, one frame every
`FRAME_INTERVAL` seconds, capped at `MAX_FRAMES`), aggregating scores by max.

Providers: `openai` | `ollama` | `local` (ONNX) | `sightengine` | `api`
(generic HTTP) | `stub` (fixed 0.05). The provider abstraction
(`deepfake/base.py` + `deepfake/factory.py`) is clean, and the GDPR warnings
on cloud providers fit the project's audience.

---

## Findings (most important first)

### 1. Silent fail-open to the stub detector — **high**

If a provider is misconfigured or unavailable, `get_detector()` falls back to
`StubDetector` with only a log warning (`deepfake/factory.py:67-73`). The stub
returns a fixed 0.05, so deepfake detection is effectively **off** while the
system appears healthy. For a child-safety tool this should be loud:

- Expose the active provider name in `GET /health`.
- Optionally add a fail-fast setting (`DEEPFAKE_REQUIRE_PROVIDER=true`) that
  refuses to start when the configured provider is unavailable.

### 2. The `local` provider's advertised auto-download does not exist — **high**

`docs/deepfake-detection.md` ("Downloads a ~50 MB ONNX model on first use")
and `engine/.env.example` ("auto-downloaded if empty") both promise an
automatic model download, but `LocalOnnxDetector.is_available()` only checks
that the file exists (`deepfake/local_detector.py:111-113`). There is no
download code anywhere and no documented URL to obtain
`efficientnet_b0_deepfake.onnx`. Consequences:

- `DEEPFAKE_PROVIDER=local` **always** silently degrades to the stub
  (compounding finding 1) unless the operator sourced a model file themselves.
- `ROADMAP.md` says the model is ~20 MB while the docs say ~50 MB.

Either ship a downloader (with a pinned URL **and checksum verification**) or
correct the docs to say the model must be provided manually via
`DEEPFAKE_MODEL_PATH`.

### 3. Errors score 0.0 — below the "no face" baseline — **medium/high**

All cloud providers append `0.0` when the API call fails or the response
can't be parsed (`cloud_openai.py:96-101`, `cloud_ollama.py:74-79`,
`cloud_sightengine.py:69-71`, `cloud_generic.py:76-78`). Since an image with
*no face at all* scores 0.05, a failed check looks **more innocent** than a
faceless image. The LLM providers are especially fragile: `float(raw)` breaks
on any answer like `"Probability: 0.7"`, which then fails open.

Suggestion: on error, return at least the 0.05 baseline — or better, a
sentinel that the route can turn into a "flag for human review" verdict.

### 4. Blocking synchronous HTTP inside async endpoints — **medium/high**

`moderate_image` / `moderate_video` are `async def`, but every provider uses
blocking `httpx.post` with 30–60 s timeouts, sequentially per face. Worst
case for video: 10 frames × N faces × 60 s (Ollama) with the event loop
blocked the whole time — one slow moderation call stalls the entire engine.
`decode_image()` / `decode_video()` have the same issue with `httpx.get`.

Suggestion: use `httpx.AsyncClient`, or run detection in a threadpool
(`run_in_executor` / `fastapi.concurrency.run_in_threadpool`).

### 5. Group photos are a blind spot — **medium**

`face_extractor.py` uses MediaPipe with `model_selection=0` (short-range,
optimised for selfies < 2 m) and skips faces smaller than 3 % of the image
(`MIN_FACE_RATIO = 0.03`). In a group-chat context, group shots with
small/distant faces are common; missed faces mean the image returns 0.05 →
allow. Consider `model_selection=1` (full-range), or run both and merge.

### 6. LLM-as-forensics is a weak signal — **medium**

GPT-4o / llava are not calibrated deepfake detectors; asking them for a
probability yields plausible-sounding but unreliable numbers. Acceptable as a
heuristic, but `docs/deepfake-detection.md` presents OpenAI as the "easiest"
option with no accuracy caveat — and verdicts auto-delete at 0.7. Add a
caveat, and consider recommending flag-only operation for LLM providers.

### 7. Smaller items — **low**

- **Doc bug:** `engine/README.md` claims `local` is the default provider; the
  actual default is `stub` (`config.py:72`).
- **SSRF vector:** `image_url` / `video_url` are fetched server-side with no
  host/IP restrictions. Mitigated by the API-key middleware, but worth
  blocking private address ranges if the engine is ever exposed.
- **Detector cache never re-checks:** the singleton is cached for the process
  lifetime, so a provider that comes online later (e.g. Ollama restarts) is
  not picked up until the engine restarts.
- **ONNX output assumption:** `local_detector.py` treats `outputs[0][0]` as a
  single logit and applies sigmoid. If the model actually emits 2-class
  softmax/logits, scores are misinterpreted — unverifiable while the model
  itself is unobtainable (finding 2).
- **Stale comment:** `cloud_sightengine.py:66` says the API returns
  `{"type_1_score": ...}` while the code reads `deepfake.score`.

---

## Testing notes — do we need sample images/videos?

- **Pipeline plumbing:** no. The mocked unit tests cover factory fallback,
  face-crop geometry, provider response parsing, and video frame sampling.
- **Detection accuracy:** yes. A live end-to-end evaluation needs
  (a) genuine face photos, (b) known AI-generated / face-swapped images,
  (c) short videos of both, and (d) a **working provider** — an OpenAI key, a
  reachable Ollama with a vision model, or SightEngine credentials. Without a
  provider every request scores 0.05 from the stub, so sample media alone
  proves nothing. The `local` ONNX path cannot currently be evaluated at all
  (finding 2).
