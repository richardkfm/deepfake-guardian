---
category_id: hate_speech
display_name: Hate Speech / Incitement
core: false
order: 120
modalities: [text]
thresholds: { minors_strict: 0.5, default: 0.6, permissive: 0.8 }
flag_threshold: 0.35
---

## Description
Racism and other group-based hatred: dehumanising generalisations about a
protected group, and calls for violence or expulsion targeting a group.
Disabled by default — enable with `ENABLED_CATEGORIES=hate_speech`.

The patterns target *framing* (group + verb of violence, group + dehumanising
noun, sweeping "all X are…" generalisations) rather than a dictionary of slurs,
so they generalise better and avoid shipping a slur list. Calls for violence are
weighted high (delete); broad generalisations are weighted lower (flag for human
review). Add locale-specific slur patterns here if your community needs them.

## Patterns (en)
- weight: 0.85  `(?i)\b(kill|murder|gas|exterminate|lynch|deport|round up|get rid of|wipe out|eliminate|behead)\b.{0,25}\b(all |the |those |these )?(jews|muslims|christians|blacks|whites|asians|arabs|latinos|mexicans|immigrants|migrants|refugees|gays|lesbians|trans(gender)? people|foreigners)\b`
- weight: 0.85  `(?i)\b(jews|muslims|christians|blacks|asians|arabs|latinos|mexicans|immigrants|migrants|refugees|gays|lesbians|trans people|foreigners)\b.{0,25}\b(should (all )?be (killed|gassed|deported|exterminated|removed|eliminated|rounded up)|must be (deported|removed|killed|gassed)|need to (be )?(deported|removed|killed|gone|wiped out))\b`
- weight: 0.8  `(?i)\b(subhuman|untermensch|vermin|cockroach(es)?|parasites?|rats|animals|scum|filth|infestation|invaders)\b.{0,25}\b(they|them|those|immigrants|migrants|muslims|jews|refugees|blacks|gays)\b`
- weight: 0.8  `(?i)\b(immigrants|migrants|muslims|jews|refugees|black people|gay people|trans people|they|them)\b.{0,20}\b(are|like|nothing but)\b.{0,15}\b(subhuman|vermin|cockroaches|parasites|rats|animals|scum|filth)\b`
- weight: 0.65  `(?i)\b(all|every|those|these|the)\s+(jews|muslims|christians|blacks|whites|asians|arabs|mexicans|immigrants|migrants|refugees|gays|trans people|women|men)\s+(are|should be|deserve|need to be|must be)\b`
- weight: 0.6  `(?i)\b(go back to (your (country|own)|where you came from)|you (people )?don'?t belong here|you'?re not welcome here|we don'?t want your kind)\b`

## Patterns (de)
- weight: 0.85  `(?i)\b(tötet|vergasen|ausrotten|abschieben|raus mit|loswerden|vernichten|aufhängen)\b.{0,25}\b(alle |die |diese )?(juden|muslime|christen|schwarze|ausländer|migranten|flüchtlinge|asylanten|schwule|lesben)\b`
- weight: 0.85  `(?i)\b(alle |die |diese )?(juden|muslime|christen|schwarze|ausländer|migranten|flüchtlinge|asylanten|schwule|lesben)\b.{0,30}\b(abschieben|abgeschoben|töten|getötet|vergasen|ausrotten|loswerden|vernichten|rausschmeißen|aufhängen)\b`
- weight: 0.8  `(?i)\b(untermenschen|ungeziefer|parasiten|ratten|gesindel|pack|abschaum|invasoren)\b`
- weight: 0.65  `(?i)\b(alle|diese|die)\s+(juden|muslime|christen|schwarze|ausländer|migranten|flüchtlinge|asylanten|schwulen)\s+(sind|sollten|gehören|muss man|müssen)\b`
- weight: 0.6  `(?i)\b(geh zurück (nach|wohin du)|du gehörst hier nicht|hier nicht willkommen|wir wollen euch hier nicht)\b`

## Educational message (en)
This message may contain hate speech, a dehumanising generalisation about a group, or a call for violence. This harms people and usually breaks platform rules and the law. If you've experienced or witnessed hate, you can get help or report it: report-it.org.uk (UK), civilrights.org (US), or your platform's reporting tools.

## Educational message (de)
Diese Nachricht enthält möglicherweise Hassrede, eine entmenschlichende Verallgemeinerung über eine Gruppe oder einen Aufruf zu Gewalt. Das verletzt Menschen und verstößt meist gegen Plattformregeln und Gesetze. Hilfe und Meldung: HateAid (hateaid.org), Meldestelle REspect! (meldestelle-respect.de) oder eine Anzeige bei der Polizei.
