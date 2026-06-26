---
category_id: sexual_violence
display_name: Sexual Violence
core: true
order: 20
modalities: [text, image, video]
thresholds: { minors_strict: 0.3, default: 0.5, permissive: 0.7 }
flag_threshold: 0.4
---

## Description
Sexual content combined with violence or coercion. The score is derived from
the sexual-content signal of the ML classifiers (see `classifiers.py`); this
file holds its thresholds and user-facing messages.

## Educational message (en)
This message contains sexual or violent content.

## Educational message (de)
Diese Nachricht enthält sexuelle oder gewalttätige Inhalte.
