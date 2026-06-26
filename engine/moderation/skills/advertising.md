---
category_id: advertising
display_name: Advertising / Spam
core: false
order: 100
modalities: [text]
thresholds: { minors_strict: 0.7, default: 0.85, permissive: 0.9 }
flag_threshold: 0.4
---

## Description
Unsolicited promotion, affiliate links, "buy now" solicitation, and crypto /
investment shilling. Disabled by default — enable with
`ENABLED_CATEGORIES=advertising`. This is a pattern-based detector; edit the
patterns below to tune it for your community.

## Patterns (en)
- weight: 0.8  `(?i)\b(buy now|order now|shop now|limited offer|limited time|act now|use code|discount code|promo code|click the link|link in bio)\b`
- weight: 0.7  `(?i)(\d{1,3}% off|free shipping|best price|lowest price|special offer)`
- weight: 0.6  `(?i)\bdm (me )?(for|to) (details|price|prices|info|order)\b`
- weight: 0.5  `(?i)\b(crypto|bitcoin|forex|investment)\b.{0,30}\b(profit|guaranteed|returns|double your)\b`

## Patterns (de)
- weight: 0.8  `(?i)\b(jetzt kaufen|jetzt bestellen|nur heute|nur für kurze zeit|rabattcode|gutscheincode|gratis versand|link in bio)\b`
- weight: 0.6  `(?i)\b(schreib mir|dm) (für|zwecks) (preis|preise|details|infos)\b`

## Structural patterns
- weight: 0.5  `(https?://\S+\s*){3,}`

## Educational message (en)
This message looks like advertising or spam. Please keep the group on-topic.

## Educational message (de)
Diese Nachricht sieht nach Werbung oder Spam aus. Bitte bleibt beim Thema.
