# likumi-lv-prasme

Prasme (skill) LLM aģentiem: Latvijas tiesību aktu (likumi.lv) meklēšana, lasīšana un korektas atsauces ar saitēm uz
likumi.lv. Lietošana aģentam: [SKILL.md](SKILL.md).

- `skripti/likumi.py`: rīks (tikai lasa, izvade JSON, Python 3.9+ bez papildu pakotnēm)
- `skripti/atsauce.py`, `skripti/teksta_atsauces.py`: atsauču veidošana un atpazīšana
- `dati/likumi.db`: datubāze; repozitorijā tās nav. Ceļu var norādīt ar `LIKUMI_DB=/ceļš/likumi.db`.

Datubāzi sagatavo un publicē datu izgūšanas repozitorijs `likumi-lv`, kurā šis repozitorijs ir apakšmodulis `prasme/`.
Šis repozitorijs par izgūšanu neko nezina; vienīgais līgums starp abiem ir datubāzes shēma (`schema_version`
publicēšanas manifestā).
