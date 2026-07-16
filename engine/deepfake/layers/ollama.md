---
layer_id: ollama
display_name: Ollama Vision (local vision model)
provider: ollama
enabled: false
weight: 1.0
order: 30
---

## Description
Uses a local Ollama instance with a vision-capable model (e.g. `llava`,
`bakllava`) to analyse face crops for deepfake indicators. Privacy-friendly:
data stays on your network when Ollama runs locally (no GDPR warning is
logged when `OLLAMA_BASE_URL` points at localhost/loopback).

## Prompt
You are an image-forensics expert. Given this photograph of a human face,
estimate the probability that the image is a deepfake or has been
AI-generated/manipulated. Respond with ONLY a single floating-point number
between 0.0 (certainly real) and 1.0 (certainly fake). Do not include any
other text.
