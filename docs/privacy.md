# Privacy & GDPR

| Data | Stored? | Details |
|------|---------|---------|
| Message text / images / video | **Never** | Processed in memory, not persisted |
| Moderation verdicts + scores | Yes (metadata) | Auto-deleted after `DATA_RETENTION_DAYS` |
| User/group IDs | Yes (hashed) | SHA-256 with secret salt — not reversible |
| Warning counts | Yes | Deleted on erasure request |

## Telegram bot commands

- `/privacy` — shows the privacy notice in the group
- `/delete_my_data` — submits an Article 17 erasure request

## Notes

- Content is **never stored** — only an 80-char preview in debug logs (never in the DB).
- User IDs are hashed before storage.
- `DEEPFAKE_PROVIDER=ollama` or `local` keeps all data on your server.
- `DEEPFAKE_PROVIDER=openai`, `sightengine`, or `api` sends face crops to that external service.

See [API Reference → GDPR endpoints](api.md#gdpr-endpoints) for the data-export
and erasure APIs.
