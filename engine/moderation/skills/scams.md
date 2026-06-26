---
category_id: scams
display_name: Scams / Phishing
core: false
order: 105
modalities: [text]
thresholds: { minors_strict: 0.7, default: 0.8, permissive: 0.9 }
flag_threshold: 0.4
---

## Description
Fraud and phishing: fake prizes, advance-fee ("pay to claim") schemes, account
"verification" phishing, impersonated support, gift-card requests, and
crypto-wallet/seed-phrase theft. Disabled by default — enable with
`ENABLED_CATEGORIES=scams`. Pattern-based; tune for your community.

## Patterns (en)
- weight: 0.75  `(?i)\b(you('?ve| have)? won|congratulations,? you'?(ve|re)|claim your (prize|reward|gift)|you are (a|the) (lucky )?winner|free (gift card|iphone|gift)|\$?\d{3,}[, ]?(cash|prize) (waiting|to claim))\b`
- weight: 0.8  `(?i)\b(pay (a )?(small )?fee to (claim|release|receive)|processing fee (to|before)|to receive (your|the) (funds|prize|inheritance)|send \$?\d+ (first|to claim)|unclaimed (funds|inheritance)|next of kin|beneficiary of (a|the))\b`
- weight: 0.8  `(?i)\b(verify your (account|identity|details|wallet)|your account (has been|will be) (suspended|locked|limited|deactivated)|confirm your (password|login|payment|card|details)|unusual (activity|sign[- ]?in)|click (here )?to (verify|secure|unlock|reactivate)|update your (billing|payment) (info|details))\b`
- weight: 0.8  `(?i)\b(send (me )?(a )?(gift ?cards?|steam cards?|google play cards?|itunes cards?)|pay (with|in|using) gift ?cards?)\b`
- weight: 0.85  `(?i)\b(seed phrase|recovery phrase|private key|connect your wallet|validate your wallet|wallet (sync|migration|verification))\b`
- weight: 0.6  `(?i)\b(official (support|team)|customer support team|this is (the )?(bank|paypal|amazon|apple|microsoft|netflix) (support|security))\b`

## Patterns (de)
- weight: 0.75  `(?i)\b(sie haben gewonnen|herzlichen glückwunsch,? sie|gewinn abholen|(gratis|kostenloses) (iphone|geschenk|gutschein)|sie sind (unser )?gewinner)\b`
- weight: 0.8  `(?i)\b(gebühr (zahlen|überweisen) um|bearbeitungsgebühr|um (ihren|den) (gewinn|betrag) zu erhalten|nicht abgeholte? (gelder|erbschaft)|erbe von)\b`
- weight: 0.8  `(?i)\b(bestätigen sie ihr (konto|passwort|identität)|ihr konto wurde (gesperrt|eingeschränkt|deaktiviert)|ungewöhnliche aktivität|klicken sie hier um.{0,25}(verifizieren|bestätigen|entsperren))\b`
- weight: 0.8  `(?i)\b(guthaben ?karten?|gutschein ?karten?|steam ?karten?)\b.{0,15}(senden|kaufen|schicken|besorgen)`

## Structural patterns
- weight: 0.55  `(?i)\b(urgent|immediately|act now|within \d+ (hours?|minutes?))\b.{0,40}https?://`

## Educational message (en)
This message looks like a scam or phishing attempt (fake prize, account "verification", advance-fee, gift-card or crypto-wallet request). Never share passwords, one-time codes, card details, or wallet seed phrases, and never send money or gift cards to claim a prize. Report it: reportfraud.ftc.gov (US), actionfraud.police.uk (UK), or econsumer.gov (international).

## Educational message (de)
Diese Nachricht sieht nach Betrug oder Phishing aus (gefälschter Gewinn, Konto-"Bestätigung", Vorkasse, Guthabenkarten- oder Krypto-Wallet-Anfrage). Teile niemals Passwörter, Einmal-Codes, Kartendaten oder Wallet-Wiederherstellungsphrasen und sende kein Geld oder Guthabenkarten, um einen "Gewinn" abzuholen. Melden: Verbraucherzentrale (verbraucherzentrale.de), watchlist-internet.at oder die Online-Wache der Polizei.
