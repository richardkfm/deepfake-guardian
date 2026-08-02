# Deepfake Detection Setup

Deepfake detection is **off by default** (`stub` mode — no models downloaded,
no API calls). To enable it, pick a provider and set the config in `engine/.env`.

## Option A: OpenAI (easiest)

```env
DEEPFAKE_PROVIDER=openai
OPENAI_API_KEY=sk-your-key-here
```

Get a key at [platform.openai.com/api-keys](https://platform.openai.com/api-keys).
Uses GPT-4o vision. No local model download needed. Face images are sent to
OpenAI — consider GDPR implications for groups with minors.

> **Accuracy caveat.** GPT-4o is not a calibrated deepfake detector. Asked for a
> probability it returns a plausible-sounding number, not a forensically
> grounded one — expect both false positives and false negatives. Prefer
> flag-only operation until you have measured it on your own content: set
> `THRESHOLD_DEEPFAKE=1.1` so nothing auto-deletes on this signal and admins
> review the flags instead. The same applies to Option B.

## Option B: Ollama (free, private)

```env
DEEPFAKE_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llava
```

Install [Ollama](https://ollama.com), then `ollama pull llava`. All data stays
on your machine. No additional downloads by the engine itself. The accuracy
caveat under Option A applies here too — `llava` is a general vision model, not
a deepfake classifier.

## Option C: Local ONNX model (advanced, max privacy)

```env
DEEPFAKE_PROVIDER=local
DEEPFAKE_MODEL_PATH=/path/to/efficientnet_b0_deepfake.onnx
```

Runs an EfficientNet-B0 model on CPU. Needs ~500 MB extra RAM and the
`onnxruntime`, `mediapipe`, `opencv-python-headless` packages (already included
in `requirements.txt`). Nothing leaves the server.

> **You must supply the model file.** The engine does **not** download it — set
> `DEEPFAKE_MODEL_PATH` to an ONNX model you provide (or place it at
> `~/.cache/deepfake_guardian/efficientnet_b0_deepfake.onnx`, the path used when
> the variable is empty). Without it this provider is unavailable and the engine
> falls back to the stub, i.e. **no detection at all** — check `GET /health`,
> which reports `deepfake.degraded: true` in that state. The model is expected
> to emit a single logit that is passed through a sigmoid; a 2-class
> softmax model will produce misinterpreted scores.

## Option D: SightEngine or custom API

```env
# SightEngine
DEEPFAKE_PROVIDER=sightengine
SIGHTENGINE_API_USER=your-user
SIGHTENGINE_API_SECRET=your-secret

# Or any HTTP endpoint
DEEPFAKE_PROVIDER=api
DEEPFAKE_API_URL=https://your-api.com/detect
DEEPFAKE_API_KEY=your-key
```

## Verifying it is actually on

A misconfigured provider does not stop the engine — it logs a warning and falls
back to the stub, which scores every face 0.05. Detection is then off while
everything looks healthy. Check which detector is live:

```bash
curl -s localhost:8000/health
```

```json
{
  "status": "ok",
  "deepfake": {
    "mode": "provider",
    "configured": "sightengine",
    "active": "stub",
    "degraded": true
  }
}
```

`degraded: true` means the provider you configured is not the one running —
fix the credentials or model path. `"active": "not_initialised"` simply means
no image has been moderated yet.

To refuse to start rather than run blind — recommended for deployments with
minors:

```env
DEEPFAKE_REQUIRE_PROVIDER=true
```

The engine then raises `DeepfakeProviderUnavailable` on the first moderation
call instead of silently degrading.

## Failure behaviour

When a provider errors or returns something unreadable, that face scores
`0.05` — the same baseline as "no face detected". It is deliberately **not**
`0.0`: an outage must never make an image look *more* innocent than an ordinary
photo. A provider that genuinely scores a face `0.0` still reports `0.0`.
