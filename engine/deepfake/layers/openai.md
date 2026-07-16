---
layer_id: openai
display_name: OpenAI Vision (GPT-4o)
provider: openai
enabled: false
weight: 1.0
order: 20
---

## Description
Uses OpenAI's GPT-4o (or configured model) vision API to score face crops for
deepfake / AI-generation indicators. Requires `OPENAI_API_KEY`.

GDPR notice: face images are sent to OpenAI's servers. Review data-processing
implications before enabling for minors-facing deployments.

## Prompt
You are an image-forensics expert. Given a photograph of a human face,
estimate the probability that the image is a deepfake or has been
AI-generated/manipulated. Respond with ONLY a single floating-point number
between 0.0 (certainly real) and 1.0 (certainly fake). Do not include any
other text.
