---
category_id: cyberbullying
display_name: Cyberbullying
core: true
order: 50
modalities: [text]
thresholds: { minors_strict: 0.4, default: 0.65, permissive: 0.8 }
flag_threshold: 0.4
---

## Description
Targeted harassment, threats, exclusion, and coercion directed at a person.
Detected by a hybrid of the ML classifier label and the regex patterns below
(see `engine/cyberbullying.py`).

## Patterns (en)
- weight: 0.9  `(?i)\b(nobody likes you|you should die|kill yourself|go kill yourself|you're worthless|you are worthless|you don't deserve to live|kys)\b`
- weight: 0.65  `(?i)\b(loser|freak|ugly|fat|stupid|idiot|moron|dumb|retard|pathetic|disgusting)\b.{0,40}\b(you|ur|u|your)\b`
- weight: 0.7  `(?i)\b(no one|nobody|everyone hates|everyone thinks|all of us)\b.{0,30}\b(you|ur|u)\b`
- weight: 0.75  `(?i)\b(i('ll| will) (send|show|share|post|leak)|if you don't|unless you)\b.{0,50}\b(everyone|all|expose|ruin)\b`

## Patterns (de)
- weight: 0.9  `(?i)\b(du solltest (sterben|tot sein|verschwinden)|ich bringe dich um|du bist es nicht wert zu leben|niemand mag dich|alle hassen dich|keiner will dich|hör auf zu leben)\b`
- weight: 0.8  `(?i)\b(keiner mag dich|niemand mag dich|du gehörst nicht dazu|du bist nicht willkommen|wir wollen dich nicht|du bist ausgeschlossen)\b`
- weight: 0.7  `(?i)\b(du bist so (hässlich|dumm|fett|bescheuert|blöd|eklig|widerlich|unnötig|nutzlos))\b`
- weight: 0.75  `(?i)\b(ich zeig das allen|ich schick das an|ich poste das|wenn du nicht|sonst zeige ich|ich mach dich fertig)\b`
- weight: 0.85  `(?i)\b(deine adresse ist|ich weiß wo du wohnst|ich kenne deine nummer)\b`

## Labels (en)
- "harassment" -> cyberbullying
- "cyberbullying" -> cyberbullying

## Labels (de)
- "insult" -> cyberbullying
- "identity_hate" -> cyberbullying
- "toxic" -> cyberbullying
- "severe_toxic" -> cyberbullying

## Educational message (en)
This message may contain cyberbullying. Be kind and respectful to others online.

## Educational message (de)
Diese Nachricht könnte Cybermobbing enthalten. Bitte geh respektvoll miteinander um.
