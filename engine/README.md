# Moderation Engine

FastAPI service that exposes HTTP endpoints for content moderation.

## Endpoints

| Method | Path              | Description                |
|--------|-------------------|----------------------------|
| POST   | `/moderate_text`  | Classify plain text        |
| POST   | `/moderate_image` | Classify an image          |
| POST   | `/moderate_video` | Classify a video           |
| GET    | `/health`         | Health check               |

## Setup

```bash
cd engine
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # edit thresholds if needed
python main.py
```

The API will be available at `http://localhost:8000`.

### System requirements (bare-metal)

- Python 3.11+
- ffmpeg (`sudo apt-get install ffmpeg` or `brew install ffmpeg`)
- 4 GB RAM minimum (8 GB recommended) — ML models use ~2–3 GB, deepfake detection adds ~500 MB
- No GPU required (CPU inference by default)

Docker is recommended — the Dockerfile handles ffmpeg and all dependencies automatically.

## Deepfake Detection

Deepfake detection uses a pluggable provider system. Set `DEEPFAKE_PROVIDER` in `.env`:

| Provider | Value | Description | Privacy |
|----------|-------|-------------|---------|
| **Stub** | `stub` **(default)** | Fixed score 0.05 — detection effectively **off** | No processing (CI/testing) |
| **OpenAI** | `openai` | GPT-4o vision | Face images sent to OpenAI |
| **Ollama** | `ollama` | Local vision model (e.g. `llava`) | Stays on your network |
| **Local ONNX** | `local` | EfficientNet-B0, CPU inference — model file must be supplied via `DEEPFAKE_MODEL_PATH` | Face data stays on-device |
| **SightEngine** | `sightengine` | Cloud API | Face images sent to SightEngine |
| **Custom API** | `api` | Your own HTTP endpoint | Face images sent to your endpoint |

The default is `stub`, so a fresh install never reports a deepfake until you
choose a provider. If the configured provider turns out to be unavailable
(missing credentials, missing model file), the engine logs a warning and falls
back to the stub — `GET /health` reports this as `deepfake.degraded: true`. Set
`DEEPFAKE_REQUIRE_PROVIDER=true` to refuse to start instead.

### Pipeline

1. MediaPipe detects faces in the image
2. Each face is cropped with padding
3. The configured provider scores each face (0.0 = real, 1.0 = deepfake)
4. The maximum score across all faces is returned

### Video moderation

Videos are decoded via OpenCV, sampled at configurable intervals, and each frame
is run through the full image moderation pipeline (NSFW + violence + deepfake).
Scores are aggregated via max across all frames.

| Setting | Default | Description |
|---------|---------|-------------|
| `FRAME_INTERVAL` | `2.0` | Seconds between sampled frames |
| `MAX_FRAMES` | `10` | Maximum frames per video |
| `MAX_VIDEO_DURATION` | `300` | Max video length in seconds |
