# pb-likumi-skill

Prasme (skill) LLM aģentiem: Latvijas tiesību aktu (likumi.lv) meklēšana, lasīšana un korektas atsauces ar saitēm uz
likumi.lv. Lietošana aģentam: [SKILL.md](SKILL.md).

- `scripts/search.py`: rīks (tikai lasa, izvade JSON, Python 3.9+ bez papildu pakotnēm)
- `scripts/atsauce.py`, `scripts/teksta_atsauces.py`: atsauču veidošana un atpazīšana
- `scripts/download.py`: ielādē vai atjaunina datubāzi pēc manifesta `latest.json` (sha256, `age -d`, `zstd -d`)
- `data/pb-likumi.db`: datubāze; repozitorijā tās nav. Ceļu var norādīt ar `LIKUMI_DB=/ceļš/likumi.db`.

Datubāzi sagatavo un publicē datu izgūšanas repozitorijs `pb-likumi`, kurā šis repozitorijs ir apakšmodulis `skill/`.
Šis repozitorijs par izgūšanu neko nezina; vienīgais līgums starp abiem ir datubāzes shēma (`schema_version`
publicēšanas manifestā).

## Uzstādīšana

1. Uzstādi `age` un `zstd` (Linux: `apt install age zstd`; macOS: `brew install age zstd`;
   Windows: `winget install FiloSottile.age Meta.Zstandard`).
2. `python3 scripts/download.py` – pirmajā reizē izveido failu `.env` šīs mapes saknē (no sagataves `.env.example`).
3. Atver `.env` un rindā `AGE_KEY=` ieraksti atslēgu, ko datu uzturētājs atsūtījis (`AGE-SECRET-KEY-1...`).
   Ja rinda `LATEST_URL=` ir tukša, ieraksti arī manifesta adresi. `.env` nav repozitorijā.
4. `python3 scripts/download.py` vēlreiz: lejupielādē datubāzi mapē `data/`; tā pati komanda to vēlāk atjaunina.

Šis repozitorijs darbojas viens pats, bez `pb-likumi-pipeline`.
