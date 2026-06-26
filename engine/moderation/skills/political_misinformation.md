---
category_id: political_misinformation
display_name: Political Misinformation
core: false
order: 110
modalities: [text]
thresholds: { minors_strict: 0.6, default: 0.8, permissive: 0.9 }
flag_threshold: 0.4
---

## Description
Conservative, pattern-based detection of well-known political/health hoaxes and
manipulation framing. Disabled by default — enable with
`ENABLED_CATEGORIES=political_misinformation`.

**Important limitation:** "misinformation" is contested and context-dependent.
This detector only matches a small set of widely-debunked claims and
manipulation phrasing; it WILL miss novel misinformation and MAY flag
legitimate discussion that quotes these phrases. The relatively high delete
thresholds mean most matches *flag for human review* rather than auto-delete.
Treat its output as a prompt for a human moderator, not a verdict. Tune the
patterns below for your community and jurisdiction.

## Patterns (en)
- weight: 0.55  `(?i)\b(wake up,? sheeple|do your own research|they don't want you to know|the truth they're hiding|mainstream media (won't|wont) tell you|open your eyes people)\b`
- weight: 0.6  `(?i)\b(the election was (stolen|rigged)|massive voter fraud|rigged election|stop the steal)\b`
- weight: 0.6  `(?i)\b(plandemic|the vaccine (is a|contains a) (hoax|microchip|tracking chip)|microchip(ped)? (by|in) the vaccine|5g (causes|spreads) (covid|corona))\b`
- weight: 0.55  `(?i)\b(false flag|crisis actor|deep state|new world order)\b`

## Patterns (de)
- weight: 0.55  `(?i)\b(wacht auf|lügenpresse|macht die augen auf|das verschweigen sie euch|die wahrheit wird verschwiegen)\b`
- weight: 0.6  `(?i)\b(die wahl wurde (gestohlen|gefälscht|manipuliert)|wahlbetrug)\b`
- weight: 0.6  `(?i)\b(plandemie|der impfstoff (enthält|ist ein) (mikrochip|hoax)|5g (verursacht|verbreitet) corona)\b`

## Educational message (en)
This message may contain political misinformation. Please verify claims with reputable, fact-checked sources before sharing.

## Educational message (de)
Diese Nachricht enthält möglicherweise politische Falschinformationen. Bitte überprüfe Behauptungen mit seriösen, geprüften Quellen, bevor du sie teilst.
