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
Sexual content combined with violence or coercion. For text the score is
derived from the sexual-content signal of the ML classifiers (see
`classifiers.py`); this file holds its thresholds and user-facing messages.

For images and video, this score also captures **AI-generated non-consensual
intimate imagery ("revenge porn" deepfakes)**: a sexualised image whose face
also scores highly on `deepfake_suspect` (see `deepfake.md`) is treated as
sexual violence even when the raw NSFW signal alone would only warrant a
flag. The combined score is `nsfw_score * deepfake_score`
(`classifiers.score_deepfake_sexual_violence`), so a media item needs *both*
a strong sexual-content signal and a strong deepfake signal to escalate —
this specifically targets non-consensual sexualised deepfakes of real
people, not ordinary sexual content or ordinary deepfakes.

A separate, deterministic path exists alongside this statistical one:
opt-in known-image hash matching (`KNOWN_IMAGE_HASH_MATCHING`, see
`engine/known_content.py`) lets a victim or admin register the perceptual
hash of a specific non-consensual image; any future upload matching that
hash — including deepfakes derived from it, re-crops, or re-encodes — is
force-deleted with reason `known_ncii_match`, bypassing thresholds
entirely. That path confirms *this exact image was previously flagged*;
this file's score-based path catches *unseen but statistically similar*
sexualised-deepfake content.

## Educational message (en)
This message contains sexual or violent content. It may also depict a
manipulated or AI-generated (deepfake) image used without the depicted
person's consent ("revenge porn"), which can be a serious violation and, in
many jurisdictions, a crime.

## Educational message (de)
Diese Nachricht enthält sexuelle oder gewalttätige Inhalte. Es könnte sich
auch um ein manipuliertes oder KI-generiertes (Deepfake-)Bild handeln, das
ohne die Zustimmung der abgebildeten Person verwendet wird ("Rachepornografie"),
was eine schwerwiegende Verletzung und in vielen Rechtsordnungen eine
Straftat darstellen kann.
