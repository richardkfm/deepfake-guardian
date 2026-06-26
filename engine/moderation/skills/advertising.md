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
Unsolicited promotion and spam. Covers the most common abusive niches:
supplements / "miracle" health products, insurance, adult/sexual services,
crypto shilling, and get-rich-quick schemes, plus generic promo and link spam.
Disabled by default — enable with `ENABLED_CATEGORIES=advertising`. Pattern-based;
strong signals (0.7+) lean toward delete, weak/ambiguous ones (≤0.5) toward a
human-review flag. Edit the patterns below to tune for your community.

## Patterns (en)
- weight: 0.6  `(?i)\b(buy now|order now|shop now|limited[- ]time offer|limited offer|act now|use (code|coupon)|discount code|promo code|click the link|link in bio|swipe up|sign up now)\b`
- weight: 0.75  `(?i)\b(get rich quick|make money fast|work from home|be your own boss|financial freedom|passive income|side hustle|guaranteed (income|profit|returns)|earn \$?\d{2,}[k]?( ?/ ?(day|week|month))?)\b`
- weight: 0.75  `(?i)\b(crypto|bitcoin|btc|ethereum|eth|altcoin|forex|nft|memecoin|pre[- ]?sale|airdrop)\b.{0,40}\b(profit|guaranteed|returns?|moon|pump|double|signal|10x|100x|invest now)\b`
- weight: 0.7  `(?i)\b(weight ?loss|fat ?burner|keto (gummies|pills)|slimming|detox tea|miracle (cure|pill|supplement)|testosterone booster|male enhancement|anti[- ]?aging|appetite suppressant)\b`
- weight: 0.8  `(?i)\b(escort|hook[- ]?up|onlyfans|only fans|sugar (daddy|baby|mommy)|cam ?girl|sex ?cam|adult content|selling nudes|nudes for sale|dm for (nudes|content|fun))\b`
- weight: 0.6  `(?i)\b(car|health|life|auto|home|travel) insurance\b|\binsurance (quote|policy|plan|deal)s?\b|\b(lower|cut|slash) your (premium|insurance)\b|\bfinal expense\b`

## Patterns (de)
- weight: 0.6  `(?i)\b(jetzt (kaufen|bestellen|sichern)|nur (heute|für kurze zeit)|rabattcode|gutscheincode|gratis versand|link in bio|jetzt anmelden)\b`
- weight: 0.75  `(?i)\b(schnell reich|schnelles geld|nebenverdienst|von zuhause (arbeiten|geld verdienen)|finanzielle freiheit|passives einkommen|garantierte (rendite|gewinne)|verdiene \d+ ?€)\b`
- weight: 0.75  `(?i)\b(krypto|bitcoin|kryptow[äa]hrung)\b.{0,40}\b(gewinn|garantiert|rendite|verdoppeln|investier)\b`
- weight: 0.7  `(?i)\b(abnehmen|fatburner|schlankheits|wundermittel|potenzmittel|nahrungserg[äa]nzung)\b`
- weight: 0.8  `(?i)\b(escort|treffen gegen cash|onlyfans|zucker(papa|baby)|cam ?girl|nacktbilder|nudes verkaufe)\b`

## Structural patterns
- weight: 0.5  `(https?://\S+\s*){3,}`
- weight: 0.5  `(?i)\b(whats ?app|telegram|signal)\b.{0,15}\+?\d[\d \-]{7,}`

## Educational message (en)
This message looks like advertising or spam (for example: promotions, crypto, supplements, get-rich-quick offers, insurance, or adult services). Please keep the group on-topic and avoid unsolicited promotions.

## Educational message (de)
Diese Nachricht sieht nach Werbung oder Spam aus (z. B. Aktionen, Krypto, Nahrungsergänzung, "schnell reich werden", Versicherungen oder Erwachsenen-Dienste). Bitte bleibt beim Thema und vermeidet unaufgeforderte Werbung.
