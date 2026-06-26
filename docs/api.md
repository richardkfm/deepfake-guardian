# API Reference

## Moderation endpoints

```
POST /moderate_text    {"text": "...", "language": "en"}
POST /moderate_image   {"image_base64": "..." | "image_url": "..."}
POST /moderate_video   {"video_base64": "..." | "video_url": "..."}
GET  /health
```

### Response format

```json
{
  "verdict": "allow",
  "reasons": [],
  "scores": {
    "violence": 0.02,
    "sexual_violence": 0.01,
    "nsfw": 0.01,
    "deepfake_suspect": 0.0,
    "cyberbullying": 0.01,
    "extra": {}
  },
  "language": "en"
}
```

`verdict` is `allow`, `flag`, or `delete`. `reasons` lists the categories that
triggered (or `elevated_<category>` for flags). `scores.extra` holds scores for
any enabled opt-in categories (see
[Configuration → skills](configuration.md#moderation-categories-skills)); it is
empty unless `ENABLED_CATEGORIES` is set.

### Try it

```bash
curl -s -X POST http://localhost:8000/moderate_text \
  -H "Content-Type: application/json" \
  -d '{"text": "hello world"}' | python3 -m json.tool
```

## GDPR endpoints

```
POST /gdpr/export              — export all data for a user (Article 15)
POST /gdpr/delete_request      — submit erasure request (Article 17)
GET  /gdpr/delete_request/{id} — check erasure status
```

See [Privacy & GDPR](privacy.md) for what is and isn't stored.

## Warning system

```
POST /warnings/record          — record a violation, returns escalation action
GET  /warnings/{user_id_hash}  — fetch warning history
```

Escalation: 1st = educational notice, 2nd = admin notification, 3rd+ =
supervisor escalation.
