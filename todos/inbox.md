# Inbox

Čo sem Rado hodí, to sem patrí — jeden riadok na vec, najnovšie hore.
Nie je to to isté ako očíslované `NNN-*.md` v tomto priečinku: tie sú nálezy
z code review, toto je zoznam želaní a nápadov, ktoré ešte nikto nerozobral.

Formát: `- [ ] YYYY-MM-DD — vec` a odrážka navyše, keď treba kontext.
Hotové sa škrtá na `- [x]`, nemaže sa — nech je vidieť, čo už padlo.

---

<!-- sem pribúdajú nové položky, najnovšie hore -->

- [ ] 2026-08-31 — epizóda sa dostane do katalógu bez svojho seriálu, takže na karte nie je plakát ani názov
  - Vidno to v Kalendári na 28. 8. 2026: karty „Episode 5" a „Episode 1" (obe HBO Max) sú prázdne šedé
    dlaždice. Nie je to chyba obrázka — epizódy plakát nemajú **nikdy**, dedia ho od seriálu, a tu
    seriál v DB nie je, takže niet od koho dediť. Z rovnakého dôvodu svieti na karte „Episode 1"
    namiesto názvu seriálu.
  - Príčina je v harveste, nie v scrape ani v parseri. Mesačný feed `/vod/?year=&month=` vidí len
    **datovaný príchod epizódy**, a seriál sám žiadny datovaný VOD event nemá — takže jeho vlastná
    URL `/film/{root}-slug/prehled/` sa do `cache/vod_urls.json` nikdy nedostane. Overené: pre všetkých
    6 chýbajúcich rootov je v harveste niekoľko detských URL a **nula** top-level.
  - Rozsah dnes: 15 titulov pod 6 chýbajúcimi rootmi (`1883585` V jednom ohni, `1846250` Call My Manager,
    `1890431` Hollywood Crime Story, `1376053` Average Joe, `1869638` Boží plán, `1886247` The Producer).
    Všetky z 26.–31. 8., čiže to pribúda s každým novým seriálom a samo sa to nespraví.
  - **Vyriešené 2026-08-31** krokom `3c. adopt orphan roots` v `cmd_update` — po dedupe dohľadá
    `root_id`, ktoré nie je vo `fact_titles`, zrekonštruuje koreňovú URL z detskej (tá ho obsahuje
    aj so slugom, takže netreba nič hádať ani znova harvestovať) a stiahne ju. Všetkých 6 koreňov
    je v cache; do DB sa načítajú najbližším parse.
  - **Ostáva canary** do `check_completeness.py`: počet titulov, ktorých `root_id` nie je vo
    `fact_titles`, musí byť nula. Nedal som ho tam, lebo v tom súbore mala v tom čase vedľajšia
    session ~51 nezacommitnutých riadkov (`alt_titles`). Dorobiť, keď to pristane.
