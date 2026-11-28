---
name: pb-likumi
description: Latvijas tiesību aktu (likumi.lv, ~126 000 akti) lokāla meklēšana, lasīšana un korektas atsauces ar saitēm uz likumi.lv. Lieto vienmēr, kad jāatrod, kurš Latvijas likums, Ministru kabineta noteikumi vai cits akts kaut ko nosaka, jānoskaidro iestādei vai tēmai saistošie akti, jāpārbauda panta teksts, grozījumi, spēkā esamība vai aktu savstarpējās sakarības, vai jāuzraksta atsauce uz pantu. Use for any question about Latvian law, legislation, regulations (Saeima, Ministru kabinets, pašvaldību saistošie noteikumi) or citations to likumi.lv.
---

# likumi.lv: Latvijas tiesību aktu meklēšana un atsauces

Šajā mapē ir visi likumi.lv publicētie tiesību akti parsētā veidā (`data/pb-likumi.db`, SQLite ar pilnteksta indeksu)
un rīks `scripts/search.py`. Rīks tikai lasa, izvade ir JSON, vajadzīgs tikai Python 3.9+ (bez papildu pakotnēm,
bez interneta). Izņēmums ir meklēšana pēc nozīmes (`--rezims nozime` un `hibrids`): tai vajag papildu pakotnes un
modeli, sk. "Meklēšanas stratēģija".

Visas komandas palaid no šīs mapes (tās, kurā atrodas šis fails):

```bash
python3 scripts/search.py <komanda> ...
```

Ja datubāze atrodas citur, norādi to ar vides mainīgo `LIKUMI_DB=/ceļš/likumi.db`.

## Ātrākais ceļš: jautājums -> normas ar atsaucēm

```bash
python3 scripts/search.py konteksts "darba devēja uzteikuma termiņš"
```

Atgriež atbilstošākos pantus un punktus ar pilnu tekstu, gatavu atsauci (`atsauce`), saiti (`url`) un Markdown saiti
(`markdown`). Padod **atslēgvārdus latviski**, nevis garu teikumu: galotnes rīks ignorē pats, bet sinonīmus nezina
(meklē gan "atlaišana", gan "uzteikums", ja nav rezultāta). Noderīgi parametri:

- `--veids likums` vai `--veids noteikumi`, `--izdevejs "Ministru kabinets"`: sašaurina aktu loku;
- `--akts 26019`: meklē tikai vienā aktā (piem. Darba likumā);
- `--limits 15`, `--uz-aktu 5`, `--garums 3000`: vairāk fragmentu, vairāk no viena akta, garāki fragmenti;
- `--statuss visi`: arī spēku zaudējušie akti; `--grozijumi`: arī grozījumu akti.

Rezultāti sakārtoti pēc atbilstības jautājumam, nevis pēc juridiskā spēka. Izlasi tekstu un pats izvērtē, vai norma
attiecas uz jautājumu.

## Meklēšanas stratēģija: pēc vārdiem vai pēc nozīmes

`konteksts` meklē trijos režīmos. Izvēlies pēc tā, kāds ir jautājums, nevis vienmēr vienu.

| Režīms | Kā meklē | Ko padot |
|---|---|---|
| `--rezims vardi` (noklusējums) | vārdu sakritība (BM25) visos aktos | atslēgvārdus, likuma terminus |
| `--rezims nozime` | tuvākās normas pēc nozīmes (vektori) | jautājumu pilnā teikumā, kā to uzdeva lietotājs |
| `--rezims hibrids` | abi kopā, rezultāti apvienoti | jautājumu pilnā teikumā |

**Sāc ar `hibrids`**, ja lietotāja jautājums ir kāds no šiem:

- sadzīves valodā, bez likuma terminiem ("vai mani var atlaist slimības laikā", "cik liela alga ir premjeram");
- situācijas apraksts vai garš jautājums ar vairākiem nosacījumiem;
- ar pārrakstīšanās kļūdām vai bez garumzīmēm;
- tāds, kur tu nezini, kā likums šo lietu sauc.

**Lieto `vardi`** (un `meklet`), ja:

- zini precīzo terminu, akta nosaukumu, panta numuru vai kodu ("pārbaudes laiks ierēdnim", "EKK 2232",
  "potēšanas žurnāls"): precīzam, retam vārdam vārdu meklēšana ir drošāka par nozīmi;
- jānoskaidro, **vai kaut kas vispār ir minēts** ("vai kādā likumā ir minētas audiogrāmatas"). To, ka normas nav,
  drīkst secināt tikai no vārdu meklēšanas: meklēšana pēc nozīmes vienmēr atgriež tuvāko, arī ja atbilstošas nav;
- jāmeklē aktos, ko vektori neaptver: rīkojumi, lēmumi, pašvaldību saistošie noteikumi, grozījumu akti, spēku
  zaudējuši akti, pielikumi, starptautisko līgumu teksti. Vektori ir tikai spēkā esošiem likumiem un Ministru
  kabineta noteikumiem;
- meklē vienā aktā (`--akts ID`) pēc konkrēta vārda.

**Lieto `nozime`** vienu pašu reti: kad `hibrids` rezultātu augšgalā ir normas, kas sakrīt tikai pēc biežiem vārdiem.

Ieteicamā secība lietotāja jautājumam:

1. `konteksts "<jautājums, kā uzdots>" --rezims hibrids` – atrod jomu un likuma terminus.
2. `konteksts "<likuma termini no 1. soļa>"` (pēc vārdiem), ja vajag, ar `--akts ID` vai `--veids` – atrod pārējās
   normas par to pašu.
3. `teksts LOK` – izlasi normas pilnā apjomā, pirms uz tām atsaucies.

Ja izvadē ir lauks `bridinajums` ("meklēšana pēc nozīmes nav pieejama"), rezultāts ir tikai pēc vārdiem: turpini ar
atslēgvārdiem un sinonīmiem. Vai datubāzē ir vektori, rāda `statuss` (lauks `vektori`).

Meklēšanai pēc nozīmes vajag: `pip install numpy torch transformers` un modeli `BAAI/bge-m3` (~2,3 GB, pirmajā reizē
lejupielādē no Hugging Face; citu ceļu norāda `PB_LIKUMI_MODELIS`). Videokarti nevajag. Katrs izsaukums ielādē modeli
no jauna, tāpēc tas ir par vairākām sekundēm lēnāks nekā meklēšana pēc vārdiem.

## Pilnā darba gaita

```bash
python3 scripts/search.py meklet "piekļūstamība tīmekļvietne"      # 1. atrodi aktus
python3 scripts/search.py akts 316109                               # 2. pase, saturs, sakarību skaits
python3 scripts/search.py teksts 316109#n4                          # 3. izlasi normu (ar lokatoriem)
python3 scripts/search.py atsauce 316109#p56/56.3                   # 4. gatava atsauce + saite
```

| Komanda | Ko dara |
|---|---|
| `konteksts VĀRDI` | Atbilstošākās normas ar tekstu un atsauci (viens izsaukums). `--rezims vardi` (noklusējums), `nozime`, `hibrids` |
| `meklet VĀRDI` | Aktu saraksts pēc nosaukuma un teksta. Visi vārdi obligāti. `--veids`, `--izdevejs`, `--tema`, `--nosaukuma` (tikai nosaukumos), `--statuss visi`, `--grozijumi`, `--limits` |
| `akts ID` | Pase, redakciju datumi, saturs (nodaļas, panti), sakarību skaits |
| `teksts LOK` | Akta vai vienības teksts ar apakšvienībām. Garam tekstam turpinājums ar `--no LOK`; `--labojumi` rāda grozījumu piezīmes |
| `atsauce LOK...` | Atsauces teksts, `url`, `markdown`, statuss, piezīmes |
| `saistitie ID` | `--veids grozits` (kas groza šo aktu), `groza`, `atcelts`, `atcel`, `pamats` (saskaņā ar ko izdots), `izdoti` (uz šī akta pamata izdotie), `st` (Satversmes tiesa) |
| `atsauces LOK` | Kuri akti tekstā atsaucas uz šo aktu vai pantu. `--izejosas`: uz ko atsaucas šis |
| `atrisinat "teksts"` | Atsauce brīvā tekstā ("Valsts pārvaldes iekārtas likuma 16. panta") -> akts, pants, saite |
| `sql "SELECT ..."` | Tikai lasīšana, ja pārējās komandas neder (shēma zemāk) |
| `statuss` | Datu apjoms un lejupielādes datumi |

Noklusēti `konteksts`, `meklet` un `atsauces` rāda tikai **spēkā esošus pamataktus**.

Vārdu meklēšana: galotnes tiek nogrieztas automātiski. Precīzai frāzei vai izvēlei lieto FTS5 sintaksi, tad vaicājums
netiek mainīts: `'"kultūras ministr"*'`, `'"personas dati" OR "personas datu"'`.

## Lokators

Vienības adrese, ko pieņem un atgriež visas komandas.

| Lokators | Nozīme |
|---|---|
| `5138` | viss akts (skaitlis ir likumi.lv ID, tas pats, kas saitē `likumi.lv/ta/id/5138`) |
| `5138#p2` | pants vai MK noteikumu punkts; `#n2` nodaļa, `#pn1` pārejas noteikumu punkts, `#piel1` pielikums |
| `5138#p2/4/1` | 2. panta ceturtās daļas 1. punkts |
| `74750#p4/4.7^1` | iesprausta vienība 4.7¹ (`^1` ir augšraksta pieraksts); pantam enkurā `#p43_1` |
| `330033/3/1/2` | akts bez enkuriem (vecais formāts): 3. panta pirmās daļas 2. punkts |
| `63545~0` | vienība bez numura pēc kārtas numura; lieto tikai tūlīt pēc tam, kad rīks to atgriezis |

Lokatoru neizdomā: ņem to no `konteksts`, `meklet`, `akts` vai `teksts` izvades.

## Atsauču noteikumi

1. Atsauces tekstu un saiti **ņem no rīka** (lauki `atsauce`, `url`, `markdown`). Nesacer saiti pats un neraksti to
   no atmiņas.
2. Saites ir tikai `https://likumi.lv/ta/id/<ID>#<enkurs>`. Neatsaucies uz šīs mapes failiem vai datubāzi.
3. Atsaucies tikai uz to, kā tekstu esi redzējis (`konteksts` vai `teksts` izvadē). Ja `konteksts` fragmentam ir
   lauks `apgriezts`, pirms secinājuma izlasi pilnu tekstu ar `teksts LOK`. `meklet` fragments nav pietiekams pamats.
4. Ja izvadē ir `piezimes`, ņem tās vērā: akts zaudējis spēku, vienība izslēgta, saite ved tikai uz akta sākumu.
5. Daļām un apakšpunktiem likumi.lv enkura nav: saite ved uz pantu (punktu), precīzo vietu norāda atsauces teksts.
6. Atbildē norādi, uz kuru dienu dati ir aktuāli (lauks `dati_uz`). Teksts ir **redakcija, kas bija spēkā
   lejupielādes dienā**; vēlāku grozījumu un vēsturisko redakciju tekstu šeit nav.
7. Ja rīks neko neatrod, pasaki to. Neaizpildi robu ar atmiņā esošu panta numuru vai tekstu.

Atsauces forma, ko rīks atgriež: `Autortiesību likuma 2. panta ceturtās daļas 1. punkts`,
`Ministru kabineta 2020. gada 14. jūlija noteikumu Nr. 445 "Kārtība, kādā iestādes ievieto informāciju internetā"
56.3. apakšpunkts`. Ja nosaukumu nevar droši locīt, forma ir `Nosaukums, 5. pants`.

## Iestādei vai tēmai saistošo aktu meklēšana

Gatavas iestāžu sasaistes datos nav. Kombinē:

1. iestādes nolikums: `meklet "Kultūras ministrijas nolikums" --nosaukuma`;
2. nolikuma izdošanas pamats un akti, uz kuriem tas atsaucas: `saistitie ID --veids pamats`, `atsauces ID --izejosas`;
3. akti, kuros iestāde minēta: `meklet '"kultūras ministr"*' --veids likums`;
4. katram atrastajam likumam uz tā pamata izdotie noteikumi: `saistitie ID --veids izdoti --statuss speka`;
5. vispārīgie akti, kas saista visas iestādes (Valsts pārvaldes iekārtas likums `63545`, Administratīvā procesa
   likums, Iesniegumu likums, Informācijas atklātības likums u.c.), pēc iestādes nosaukuma neatradīsies: pievieno tos
   pēc būtības, atrodot ar `meklet "…" --nosaukuma`.

Tēmai: `konteksts` ar vairākiem atslēgvārdu variantiem, tad katram būtiskajam likumam `saistitie ID --veids izdoti`
(MK noteikumi, kas to detalizē) un `atsauces LOK` (kas vēl atsaucas uz konkrēto pantu).

## Datu robežas

- Dati ir momentuzņēmums. Datumu rāda `statuss` un lauks `dati_uz`. Ja jautājums ir par nesenām izmaiņām, brīdini,
  ka aktuālais teksts jāpārbauda likumi.lv saitē.
- **Vecā formāta akti** (`formats = neko-body`, ~80% aktu, galvenokārt rīkojumi un veci akti): struktūra noteikta
  pēc numuriem, enkuru nav, saite ved uz akta sākumu.
- **Pielikumu** saturs (tabulas, veidlapas) nav iekļauts: ir tikai pielikuma esamība un saite uz to.
- **Sakarības** (`saistitie`) ir rekonstruētas no aktu satura. Izlasē pret likumi.lv: grozījumi ~99% precīzi,
  pārējās ~85–95%; atcelto aktu saraksts (`atcel`) ir nepilnīgs.
- **Ienākošās atsauces** (`atsauces`) ir tikai tās, kas likumi.lv tekstā ir saites.
- **Tēmas** (`--tema`) ir tikai ~12% aktu; tēmai drošāk meklēt pēc vārdiem.
- Meklēšana pēc vārdiem (BM25) sinonīmus nezina: izmēģini sinonīmus un likuma terminus vai lieto `--rezims hibrids`.
- Meklēšana pēc nozīmes aptver tikai spēkā esošus likumus un Ministru kabineta noteikumus (bez pielikumiem un
  starptautisko līgumu tekstiem) un nepasaka, ka atbilstošas normas nav.
- Datos nav ES regulu un direktīvu, tiesu nolēmumu (izņemot Satversmes tiesas) un aktu, kas nav publicēti likumi.lv.

## Datubāzes shēma (komandai `sql`)

```
akti(likumi_id PK, nosaukums, izdevejs, veids, numurs, pienemts, stajas_speka, zaude_speku, statuss, publicets,
     tema JSON, atbildiga_iestade, izdots_saskana_ar, aizstats_ar, formats, lejupieladets)
vienibas(id PK, likumi_id, parent_id, tips, numurs, enkurs, limenis, virsraksts, teksts, labojumi, seciba)
     tips: nodala | pants | dala | punkts | apakspunkts | parejas | pielikums | virsraksts | teksts | ...
vienibas_fts(virsraksts, teksts)            FTS5, rowid = vienibas.id
attiecibas(no_id, kods, uz_id, noteikums)            kods: 468 grozīts ar | rev-468 groza | 923 atcelts ar | rev-923 atceļ |
                                            933 izdots saskaņā ar | rev-933 uz tā pamata izdoti | rev-stnol ST nolēmumi
atsauces(likumi_id, no_vienibas, uz_likumi_id, uz_enkurs, veids, teksts)    saites aktu tekstā
redakcijas(likumi_id, no, lidz, tips)       redakciju datumi (bez teksta)
vienibu_grozijumi(vienibas_id, likumi_id, groz_likumi_id, groz_datums, stajas_speka, darbiba)   kurš akts kuru vienību grozījis
fragmenti(id, likumi_id, lokators, nr, no_seciba, lidz_seciba)   vektorizētie fragmenti: norma un vienību diapazons
vektoru_bloki(nr, skaits, ids, dati)        fragmentu vektori (int8); lieto tikai konteksts --rezims nozime | hibrids
meta(atslega, vertiba)                      schema_version, dati_uz, embedding_model, ...
```

`vienibas.id` nav stabils starp datu versijām: ārpus viena izsaukuma lieto lokatoru.

Piemērs: spēkā esošo likumu skaits pa gadiem

```bash
python3 scripts/search.py sql "SELECT substr(pienemts,1,4) g, COUNT(*) FROM akti WHERE veids='likums' AND statuss='spēkā esošs' GROUP BY 1 ORDER BY 1 DESC" --limits 10
```
