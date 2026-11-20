# pb-likumi-skill

Prasme (skill) LLM aģentiem: Latvijas tiesību aktu (likumi.lv) meklēšana, lasīšana un korektas atsauces ar saitēm uz
likumi.lv. Lietošana aģentam: [SKILL.md](SKILL.md).

- `scripts/likumi.py`: rīks (tikai lasa, izvade JSON, Python 3.9+ bez papildu pakotnēm)
- `scripts/atsauce.py`, `scripts/teksta_atsauces.py`: atsauču veidošana un atpazīšana
- `data/pb-likumi.db`: datubāze; repozitorijā tās nav. Ceļu var norādīt ar `LIKUMI_DB=/ceļš/likumi.db`.

Datubāzi sagatavo un publicē datu izgūšanas repozitorijs `pb-likumi`, kurā šis repozitorijs ir apakšmodulis `skill/`.
Šis repozitorijs par izgūšanu neko nezina; vienīgais līgums starp abiem ir datubāzes shēma (`schema_version`
publicēšanas manifestā).
