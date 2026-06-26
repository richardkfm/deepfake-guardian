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
Conspiracy theories, manipulation framing, and well-known debunked claims
("fake news"). Disabled by default — enable with
`ENABLED_CATEGORIES=political_misinformation`.

**Important limitation:** "misinformation" is contested and context-dependent.
These patterns match recognisable conspiracy/manipulation phrasing and a set of
widely-debunked claims — they WILL miss novel misinformation and MAY match
legitimate discussion that quotes these phrases. The relatively high delete
thresholds mean most matches *flag for human review* rather than auto-delete.
Treat the output as a prompt to fact-check, not a verdict. (Hate speech, racism,
and calls for violence are handled by the separate `hate_speech` skill.)

## Patterns (en)
- weight: 0.5  `(?i)\b(wake up,? sheeple|do your own research|they don'?t want you to know|the truth they'?re hiding|main ?stream media (won'?t|wont|never) (tell|report)|open your eyes people|follow the money|connect the dots|what they'?re not telling you|plandemic|scamdemic)\b`
- weight: 0.6  `(?i)\b(deep state|new world order|the great reset|false flag|crisis actors?|chem ?trails|flat earth|qanon|adrenochrome|illuminati|reptilians?|lizard people)\b`
- weight: 0.6  `(?i)\b(the election was (stolen|rigged)|stop the steal|massive voter fraud|rigged election|dominion (voting|machines) (fraud|rigged))\b`
- weight: 0.65  `(?i)\b(the vaccine (is a|contains a?|causes) (hoax|micro ?chip|tracking chip|autism|infertility)|micro ?chip(ped)? (in|by|from) (the )?vaccine|5g (causes|spreads|is behind) (covid|corona)|covid(-19)? is a hoax|drink bleach to cure|miracle cure for (covid|cancer))\b`

## Patterns (de)
- weight: 0.5  `(?i)\b(wacht auf|lügenpresse|macht die augen auf|das verschweigen (sie|die)( euch)?|die wahrheit wird verschwiegen|macht euch schlau|plandemie|scheindemie)\b`
- weight: 0.6  `(?i)\b(tiefer staat|neue weltordnung|der große austausch|the great reset|falsche flagge|krisendarsteller|chemtrails|flacherde|reptiloiden)\b`
- weight: 0.6  `(?i)\b(die wahl wurde (gestohlen|gefälscht|manipuliert)|wahlbetrug)\b`
- weight: 0.65  `(?i)\b(der impfstoff (enthält|ist ein|verursacht) (mikrochip|hoax|unfruchtbarkeit|autismus)|5g (verursacht|verbreitet) corona|corona ist ein? (fake|schwindel))\b`

## Educational message (en)
This message may contain misinformation or a conspiracy claim. Please verify before sharing. Trusted fact-checkers: Snopes (snopes.com), Reuters Fact Check (reuters.com/fact-check), AFP Fact Check (factcheck.afp.com), and PolitiFact (politifact.com). This detector is intentionally conservative — treat it as a prompt for human review, not a final judgement.

## Educational message (de)
Diese Nachricht enthält möglicherweise Falschinformationen oder eine Verschwörungserzählung. Bitte prüfe sie, bevor du sie teilst. Seriöse Faktenchecker: Correctiv (correctiv.org/faktencheck), dpa-Faktencheck (dpa-factchecking.com), Tagesschau Faktenfinder (tagesschau.de/faktenfinder) und Mimikama (mimikama.org). Dieser Filter ist bewusst zurückhaltend — bitte als Hinweis für eine menschliche Prüfung verstehen.
