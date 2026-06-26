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

## Option B: Ollama (free, private)

```env
DEEPFAKE_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llava
```

Install [Ollama](https://ollama.com), then `ollama pull llava`. All data stays
on your machine. No additional downloads by the engine itself.

## Option C: Local ONNX model (advanced, max privacy)

```env
DEEPFAKE_PROVIDER=local
```

Runs an EfficientNet-B0 model on CPU. Downloads a ~50 MB ONNX model on first
use. Needs ~500 MB extra RAM and the `onnxruntime`, `mediapipe`,
`opencv-python-headless` packages (already included in `requirements.txt`).
Nothing leaves the server.

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
