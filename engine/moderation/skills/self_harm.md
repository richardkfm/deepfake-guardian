---
category_id: self_harm
display_name: Self-harm / Eating-disorder Promotion
core: false
order: 130
modalities: [text]
thresholds: { minors_strict: 0.6, default: 0.8, permissive: 0.9 }
flag_threshold: 0.4
---

## Description
**Promotion, encouragement, or glorification** of suicide, self-harm, or
disordered eating (e.g. pro-ana/pro-mia content, "thinspo", method-sharing,
telling someone to end their life). Disabled by default — enable with
`ENABLED_CATEGORIES=self_harm`. Especially relevant for groups with minors.

**Important:** this targets content that *promotes harm to others or glorifies
it*, not someone expressing their own distress. A person saying "I feel awful"
or "I want to die" needs **support, not moderation** — do not treat that as a
violation. Because the line is delicate, thresholds are set so most matches
*flag for human review*, and the educational message routes to crisis help.

## Patterns (en)
- weight: 0.7  `(?i)\b(thinspo|thinspiration|pro[- ]?ana|pro[- ]?mia|meanspo|bonespo|nothing tastes as good as skinny|how to (purge|starve)|starve (yourself|together)|fasting tips to lose|skip meals to lose|goal weight \d{2,3})\b`
- weight: 0.85  `(?i)\b(you should (just )?(kill yourself|end it|kms)|go (ahead and )?(kill yourself|kys)|the world (would be )?better (off )?without you|do it,? (no one|nobody) (cares|will miss you)|nobody would miss you|just end your life)\b`
- weight: 0.7  `(?i)\b(how to (cut|hurt) (yourself|myself) (deeper|better|without)|best way to (cut|self[- ]?harm|od|overdose)|cutting tips|self[- ]?harm is (beautiful|the only way)|blades? are (my|the only)|i'?ll teach you how to (cut|purge|starve))\b`

## Patterns (de)
- weight: 0.7  `(?i)\b(magersucht (tipps|pro)|pro[- ]?ana|pro[- ]?mia|thinspo|hungern (tipps|zusammen)|nichts schmeckt so gut wie dünn|wie man (hungert|erbricht)|mahlzeiten auslassen um)\b`
- weight: 0.85  `(?i)\b(bring dich (doch )?um|töte dich|niemand (würde dich vermissen|vermisst dich)|die welt wäre besser ohne dich|mach (doch )?schluss|beende dein leben)\b`
- weight: 0.7  `(?i)\b(wie man sich (ritzt|schneidet)|beste art sich zu (verletzen|ritzen)|ritz ?tipps|selbstverletzung ist)\b`

## Educational message (en)
This message appears to promote or encourage self-harm, suicide, or disordered eating. If you or someone you know is struggling, help is available 24/7: in the US/Canada call or text 988; in the UK & Ireland call Samaritans on 116 123; or find a local helpline at findahelpline.com. You are not alone, and things can get better.

## Educational message (de)
Diese Nachricht scheint Selbstverletzung, Suizid oder Essstörungen zu fördern oder zu verharmlosen. Wenn es dir oder jemandem, den du kennst, schlecht geht, gibt es rund um die Uhr Hilfe: TelefonSeelsorge 0800 111 0 111 oder 0800 111 0 222 (kostenlos, anonym); Kinder- und Jugendtelefon 116 111; international findahelpline.com. Du bist nicht allein, und es kann besser werden.
