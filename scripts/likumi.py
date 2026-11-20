#!/usr/bin/env python3
"""Rīks aģentiem: Latvijas tiesību aktu meklēšana, lasīšana, sakarības un korektas atsauces ar likumi.lv saitēm.

Izvade ir JSON. Datubāzi atver tikai lasīšanai. Ārēju atkarību nav (python3 scripts/likumi.py ...).

  likumi.py meklet "piekļūstamība tīmekļvietne"        akti pēc teksta un nosaukuma (noklusēti: spēkā esoši pamatakti)
  likumi.py meklet "Kultūras ministrija" --veids likums
  likumi.py konteksts "darba devēja pienākums uzteikums"  RAG: atbilstošākās normas ar tekstu un atsauci
  likumi.py akts 5138                                    pase, saturs (nodaļas, panti), sakarību skaits
  likumi.py teksts 5138#p2                               vienības teksts ar apakšvienībām un lokatoriem
  likumi.py atsauce 5138#p2/4/1 316109#p56/56.3          gatava atsauce + https://likumi.lv/ta/id/... saite
  likumi.py saistitie 63545 --veids izdoti               groza / grozīts ar / atceļ / atcelts ar / pamats / izdoti
  likumi.py atsauces 63545#p16                           kuri akti tekstā atsaucas uz šo pantu (vai --izejosas)
  likumi.py atrisinat "saskaņā ar Valsts pārvaldes iekārtas likuma 16. panta pirmo daļu"
  likumi.py sql "SELECT veids, COUNT(*) FROM akti GROUP BY 1"      tikai lasīšana
  likumi.py statuss                                      datu apjoms un svaigums

Lokatoru formāts un atsauču noteikumi: sk. SKILL.md.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from atsauce import STRUKT, VIRSR, Akts, atsauce, nr  # noqa: E402

SAKNE = Path(__file__).resolve().parent.parent


def _db_cels() -> Path:
    """1) LIKUMI_DB; 2) prasmes pašas data/pb-likumi.db (ielādēta publiskā DB);
    3) ja prasme ir apakšmodulis datu izgūšanas repozitorijā: tā darba DB."""
    if os.environ.get("LIKUMI_DB"):
        return Path(os.environ["LIKUMI_DB"])
    sava = SAKNE / "data" / "pb-likumi.db"
    izgusanas = SAKNE.parent / "data" / "work" / "likumi.db"
    return izgusanas if (not sava.exists() and izgusanas.exists()) else sava


DB = _db_cels()
ATBALSTITA_SHEMA = 1    # augstākā publiskās DB schema_version, ko šis rīks saprot
GROZ_SQL = "(a.nosaukums LIKE 'Grozījum%' OR a.nosaukums LIKE 'Par grozījum%')"
# konteksts: akta veida svars sakārtošanā un palīgvārdi, ko atmet no jautājuma
SVARS = {"likums": 1.3, "noteikumi": 1.15, "saistošie noteikumi": 0.9, "instrukcija": 1.0, "rīkojums": 0.7, "lēmums": 0.7}
PALIGVARDI = set("""un vai ir nav kas ko kā kad kur kāds kāda kādi kādas kādu kādai kādam kuri kuras kurš kura kuru par
    pie no uz ar bez pēc līdz starp caur pret pa ka lai ja bet arī tikai tas tā tie tās to šis šī šie šīs šo jā nē
    cik kāpēc kādēļ vajag drīkst var būt jābūt tiek tika saskaņā attiecībā prasības noteikts noteikta nosaka""".split())
# nosaukums rīkā -> (attiecibas.kods, nozīme)
SAITES = {
    "grozits": ("468", "akti, kas groza šo aktu"),
    "groza": ("rev-468", "akti, kurus šis akts groza"),
    "atcelts": ("923", "akts, ar kuru šis akts zaudējis spēku"),
    "atcel": ("rev-923", "akti, kuri zaudējuši spēku ar šo aktu"),
    "pamats": ("933", "akti, saskaņā ar kuriem šis akts izdots"),
    "izdoti": ("rev-933", "akti, kas izdoti uz šī akta pamata"),
    "st": ("rev-stnol", "Satversmes tiesas nolēmumi par šo aktu"),
}


def savienot() -> sqlite3.Connection:
    if not DB.exists():
        sys.exit(f"nav datubāzes {DB} (norādi LIKUMI_DB=/ceļš/likumi.db)")
    c = sqlite3.connect(f"file:{DB}?mode=ro", uri=True, timeout=30)
    try:    # publiskajā DB ir tabula meta; izgūšanas repozitorija darba DB tās nav
        v = c.execute("SELECT vertiba FROM meta WHERE atslega='schema_version'").fetchone()
    except sqlite3.OperationalError:
        v = None
    if v and int(v[0]) > ATBALSTITA_SHEMA:
        sys.exit(f"datubāzes shēmas versija {v[0]} ir jaunāka par šīs prasmes atbalstīto ({ATBALSTITA_SHEMA}): "
                 "atjaunini prasmi (git pull)")
    c.row_factory = sqlite3.Row
    return c


def izvade(x):
    json.dump(x, sys.stdout, ensure_ascii=False, indent=1)
    print()


def kluda(teksts: str):
    izvade({"kluda": teksts})
    sys.exit(1)


def akta_id(lok: str) -> int:
    m = re.match(r"^(\d+)", lok)
    if not m:
        kluda(f"'{lok}': lokatoram jāsākas ar likumi_id, piem. 5138 vai 5138#p2")
    return int(m.group(1))


def ielade(c, lok: str):
    try:
        a = Akts(c, akta_id(lok))
        return a, a.atrast(lok)
    except LookupError as e:
        kluda(str(e))


def akta_rinda(c, lid: int, kes: dict) -> dict:
    """Īss akta apraksts sarakstiem (ar atsauci uz visu aktu)."""
    if lid not in kes:
        r = c.execute("SELECT * FROM akti WHERE likumi_id=?", (lid,)).fetchone()
        if r is None:
            kes[lid] = {"likumi_id": lid, "piezime": "akts nav datubāzē"}
        else:
            a = Akts.__new__(Akts)
            a.pase, a.id, a.redakcija_no, a.V = dict(r), lid, None, {}
            at = atsauce(a, None)
            kes[lid] = {"likumi_id": lid, "atsauce": at["atsauce"], "url": at["url"], "veids": r["veids"],
                        "izdevejs": r["izdevejs"], "statuss": r["statuss"], "pienemts": r["pienemts"],
                        "stajas_speka": r["stajas_speka"], "zaude_speku": r["zaude_speku"]}
    return kes[lid]


# ------------------------------------------------------------------ meklet
def fts_vaicajums(q: str) -> str:
    """Brīvs teksts -> FTS5 vaicājums. Latviešu locījumiem vārda galotni aizstāj ar prefiksa meklēšanu:
    'piekļūstamība tīmekļvietnēs' -> 'piekļūstamī* tīmekļvietn*'. Ja vaicājumā ir FTS sintakse, to nemaina."""
    if re.search(r'["*()]|\b(OR|AND|NOT|NEAR)\b', q):
        return q
    out = []
    for w in re.findall(r"[\w\-]+", q.lower()):
        if w.isdigit() or len(w) < 5:
            out.append(f'"{w}"')
        else:
            out.append(f'"{w[:-2] if len(w) >= 7 else w[:-1]}"*')
    return " ".join(out)


def filtri(a) -> tuple[str, list]:
    f, p = [], []
    if a.statuss == "speka":
        f.append("a.statuss = 'spēkā esošs'")
    elif a.statuss == "zaudejis":
        f.append("a.statuss = 'zaudējis spēku'")
    if not a.grozijumi:
        f.append(f"NOT {GROZ_SQL}")
    for lauks, v in (("veids", a.veids), ("izdevejs", a.izdevejs)):
        if v:
            f.append(f"a.{lauks} LIKE ?")
            p.append(v)
    if a.tema:
        f.append("a.tema LIKE ?")
        p.append(f"%{a.tema}%")
    return (" AND " + " AND ".join(f)) if f else "", p


def cmd_meklet(c, a):
    q = " ".join(a.vaicajums)
    fsql, fpar = filtri(a)
    akti: dict[int, dict] = {}
    # 1) nosaukumā: visi vārdu celmi
    celmi = [w[:-2] if len(w) >= 7 else (w[:-1] if len(w) >= 5 else w) for w in re.findall(r"[\w\-]+", q)]
    if celmi:
        for r in c.execute(
                "SELECT a.likumi_id FROM akti a WHERE " + " AND ".join("a.nosaukums LIKE ?" for _ in celmi) + fsql +
                " ORDER BY (a.veids='likums') DESC, length(a.nosaukums) LIMIT 200", [f"%{x}%" for x in celmi] + fpar):
            akti[r[0]] = {"nosaukuma": True, "n": 0, "labakais": 0.0, "vien": []}
    # 2) tekstā: FTS
    fq = fts_vaicajums(q)
    if not a.nosaukuma:
        try:
            rindas = c.execute(
                f"""SELECT v.likumi_id, v.id, bm25(vienibas_fts) AS r,
                           snippet(vienibas_fts, -1, '**', '**', ' … ', 24) AS fr
                    FROM vienibas_fts JOIN vienibas v ON v.id = vienibas_fts.rowid
                    JOIN akti a ON a.likumi_id = v.likumi_id
                    WHERE vienibas_fts MATCH ? {fsql} ORDER BY r LIMIT 20000""", [fq] + fpar).fetchall()
        except sqlite3.OperationalError as e:
            kluda(f"FTS vaicājuma kļūda ({fq}): {e}")
        for r in rindas:
            x = akti.setdefault(r["likumi_id"], {"nosaukuma": False, "n": 0, "labakais": 0.0, "vien": []})
            x["n"] += 1
            x["labakais"] = min(x["labakais"], r["r"])
            if len(x["vien"]) < a.vienibas:
                x["vien"].append((r["id"], r["fr"]))
    seciba = sorted(akti, key=lambda i: (not akti[i]["nosaukuma"], akti[i]["labakais"] * (1 + 0.3 * math.log1p(akti[i]["n"]))))
    kes: dict = {}
    out = []
    for lid in seciba[:a.limits]:
        x = akti[lid]
        r = dict(akta_rinda(c, lid, kes))
        r["sakritiba_nosaukuma"] = x["nosaukuma"]
        r["sakritibas_teksta"] = x["n"]
        if x["vien"]:
            ak = Akts(c, lid)
            r["vienibas"] = []
            for vid, fr in x["vien"]:
                at = atsauce(ak, ak.V[vid])
                r["vienibas"].append({"lokators": at["lokators"], "atsauce": at["atsauce"], "url": at["url"],
                                      "fragments": re.sub(r"\s+", " ", fr or "")})
        out.append(r)
    izvade({"vaicajums": q, "fts": None if a.nosaukuma else fq, "atrasti_akti": len(akti), "paraditi": len(out),
            "filtri": {"statuss": a.statuss, "grozijumu_akti": bool(a.grozijumi), "veids": a.veids,
                       "izdevejs": a.izdevejs, "tema": a.tema},
            "akti": out})


# ------------------------------------------------------------------ konteksts (RAG)
def cmd_konteksts(c, a):
    """Jautājums -> atbilstošākās normas ar pilnu tekstu un gatavu atsauci (viens izsaukums RAG vajadzībām)."""
    q = " ".join(a.vaicajums)
    fsql, fpar = filtri(a)
    if a.akts:
        fsql += " AND a.likumi_id = ?"
        fpar.append(a.akts)
    brivs0 = not re.search(r'["*()]|\b(OR|AND|NOT|NEAR)\b', q)
    if brivs0:  # dabiskas valodas jautājumam atmet palīgvārdus
        vardi = [w for w in re.findall(r"[\w\-]+", q) if w.lower() not in PALIGVARDI]
        q = " ".join(vardi) or q
    fq = fts_vaicajums(q)
    brivs = fq != q or not re.search(r'["*()]|\b(OR|AND|NOT|NEAR)\b', q)

    def vaicat(fts):
        try:
            return c.execute(
                f"""SELECT v.likumi_id, v.id, bm25(vienibas_fts, 3.0, 1.0) AS r
                    FROM vienibas_fts JOIN vienibas v ON v.id = vienibas_fts.rowid
                    JOIN akti a ON a.likumi_id = v.likumi_id
                    WHERE vienibas_fts MATCH ? {fsql} ORDER BY r LIMIT 3000""", [fts] + fpar).fetchall()
        except sqlite3.OperationalError as e:
            kluda(f"FTS vaicājuma kļūda ({fts}): {e}")

    rindas, rezims = vaicat(fq), "visi vārdi"
    if len(rindas) < a.limits and brivs and " " in fq:
        fq2 = " OR ".join(fq.split(" "))
        redzeti = {r["id"] for r in rindas}
        rindas = list(rindas) + [r for r in vaicat(fq2) if r["id"] not in redzeti]
        fq, rezims = fq2, "jebkurš no vārdiem (ar visiem vārdiem atrasts par maz)"
    # normatīvie akti pirms rīkojumiem un lēmumiem (bm25 ir negatīvs: mazāks = labāks)
    svars = {r[0]: SVARS.get(r[1], 0.8) for r in c.execute(
        f"SELECT likumi_id, veids FROM akti WHERE likumi_id IN ({','.join(str(i) for i in {r['likumi_id'] for r in rindas})})")}
    rindas = sorted(rindas, key=lambda r: r["r"] * svars.get(r["likumi_id"], 0.8))
    akti: dict[int, Akts] = {}
    uz_aktu: dict[int, int] = {}
    redz: set = set()
    out = []
    for r in rindas:
        lid = r["likumi_id"]
        if uz_aktu.get(lid, 0) >= a.uz_aktu:
            continue
        if lid not in akti:
            if len(akti) >= 60:
                continue
            akti[lid] = Akts(c, lid)
        ak = akti[lid]
        if r["id"] not in ak.V:
            continue
        # fragmenta sakne: tuvākais pants vai augšējā līmeņa punkts; citādi pati vienība
        sakne = next((x for x in ak.kede(r["id"]) if x["tips"] in ("pants", "punkts")), ak.V[r["id"]])
        if (lid, sakne["id"]) in redz:
            continue
        redz.add((lid, sakne["id"]))
        uz_aktu[lid] = uz_aktu.get(lid, 0) + 1
        ids = sorted([sakne["id"]] + ak.apaksvienibas(sakne["id"]), key=lambda i: ak.V[i]["seciba"])
        gab, garums, apgr = [], 0, False
        for i in ids:
            x = ak.V[i]
            galva = " ".join(s for s in (apzimejums(ak, x), x["virsraksts"]) if s)
            t = f"{'  ' * max(0, x['limenis'] - sakne['limenis'])}{galva} {(x['teksts'] or '').strip()}".rstrip()
            if gab and garums + len(t) > a.garums:
                apgr = True
                break
            gab.append(t)
            garums += len(t)
        at = atsauce(ak, sakne)
        trap = ak.V[r["id"]]
        out.append({
            "atsauce": at["atsauce"], "url": at["url"], "markdown": at["markdown"], "lokators": at["lokators"],
            "statuss": at["statuss"],
            **({"trapijums": atsauce(ak, trap)["atsauce"]} if trap["id"] != sakne["id"] else {}),
            "teksts": "\n".join(gab)[:a.garums * 2],
            **({"apgriezts": f"pilns teksts: teksts {at['lokators']}"} if apgr else {}),
            **({"piezimes": at["piezimes"]} if at.get("piezimes") else {}),
        })
        if len(out) >= a.limits:
            break
    izvade({"vaicajums": q, "fts": fq, "rezims": rezims, "paraditi": len(out),
            "dati_uz": out and atsauce(akti[next(iter(akti))], None).get("dati_uz") or None,
            "fragmenti": out,
            "piezime": "Fragmenti sakārtoti pēc atbilstības vārdiem (BM25), nevis pēc juridiskā spēka. Pirms apgalvojuma "
                       "pārliecinies, ka norma attiecas uz jautājumu; plašākam kontekstam: teksts LOK, akts ID."})


# ------------------------------------------------------------------ akts
def cmd_akts(c, a):
    ak, _ = ielade(c, str(a.id))
    p = ak.pase
    saturs = []
    for v in ak.V.values():
        if v["tips"] in VIRSR or v["tips"] in ("pants", "pielikums"):
            saturs.append({"lokators": ak.lokators(v["id"]), "tips": v["tips"], "numurs": v["numurs"],
                           "virsraksts": v["virsraksts"] or (v["teksts"] or "")[:80] or None})
    skaits: dict[str, int] = {}
    for v in ak.V.values():
        skaits[v["tips"]] = skaits.get(v["tips"], 0) + 1
    sait = {}
    for nos, (kods, apr) in SAITES.items():
        n = c.execute("SELECT COUNT(DISTINCT uz_id) FROM attiecibas WHERE no_id=? AND kods=?", (ak.id, kods)).fetchone()[0]
        if n:
            sait[nos] = {"skaits": n, "nozime": apr}
    red = [dict(r) for r in c.execute("SELECT no, lidz, tips FROM redakcijas WHERE likumi_id=? ORDER BY no", (ak.id,))]
    pilns = len(saturs) <= a.saturs_limits
    izvade({
        **atsauce(ak, None),
        "likumi_id": ak.id, "nosaukums": p["nosaukums"], "veids": p["veids"], "izdevejs": p["izdevejs"],
        "numurs": p["numurs"], "pienemts": p["pienemts"], "stajas_speka": p["stajas_speka"],
        "zaude_speku": p["zaude_speku"], "publicets": p["publicets"], "tema": json.loads(p["tema"] or "[]"),
        "atbildiga_iestade": p["atbildiga_iestade"], "izdots_saskana_ar": p["izdots_saskana_ar"],
        "aizstats_ar": p["aizstats_ar"], "pazinojums": p["pazinojums"],
        "formats": p["formats"],
        "redakcijas": {"skaits": len(red), "pirma": red[0]["no"] if red else None,
                       "speka_esosa_no": ak.redakcija_no, "nakotnes": [r["no"] for r in red if r["tips"] == "Nākotnes"]},
        "vienibu_skaits": skaits,
        "saistitie": sait,
        "saturs": saturs if pilns else saturs[:a.saturs_limits],
        **({} if pilns else {"saturs_apgriezts": f"parādīti {a.saturs_limits} no {len(saturs)}; --saturs-limits N"}),
    })


# ------------------------------------------------------------------ teksts
def apzimejums(ak: Akts, v: dict) -> str:
    n, t = v["numurs"], v["tips"]
    if not n:
        return ""
    if t == "pants":
        return f"{nr(n)} pants."
    if t == "dala":
        return f"({n})"
    if t == "pielikums":
        return f"{nr(n)} pielikums."
    if t in VIRSR:
        return n + ("." if n.isdigit() else "")
    vec = ak.V.get(v["parent_id"])
    if n.isalpha() or (vec and vec["tips"] in ("pants", "dala") and "." not in n) or (
            t == "apakspunkts" and "." not in n):
        return f"{n})"
    return f"{n}."


def cmd_teksts(c, a):
    ak, v = ielade(c, a.lokators)
    if v is None:
        ids = list(ak.V)
    else:
        ids = [v["id"]] + ak.apaksvienibas(v["id"])
        ids.sort(key=lambda i: ak.V[i]["seciba"])
    if a.no:
        _, v0 = ielade(c, a.no)
        if v0 is None or v0["id"] not in ak.V:
            kluda("--no jābūt vienības lokatoram tajā pašā aktā")
        ids = [i for i in ids if ak.V[i]["seciba"] >= v0["seciba"]]
    baze = ak.V[ids[0]]["limenis"] if ids else 0
    rindas, garums, turpinat = [], 0, None
    for i in ids:
        x = ak.V[i]
        if x["tips"] in ("parakstitajs", "vieta_datums") and v is None and not a.viss:
            continue
        galva = " ".join(s for s in (apzimejums(ak, x), x["virsraksts"]) if s)
        t = (x["teksts"] or "").strip()
        r = f"{'  ' * max(0, x['limenis'] - baze)}[{ak.lokators(i)}] " + (
            f"{galva}\n{'  ' * max(0, x['limenis'] - baze)}  {t}" if x["virsraksts"] and t else f"{galva} {t}".strip())
        if x["labojumi"] and a.labojumi:
            r += f"\n{'  ' * max(0, x['limenis'] - baze)}  {x['labojumi']}"
        if not a.viss and garums + len(r) > a.limits and rindas:
            turpinat = ak.lokators(i)
            break
        rindas.append(r)
        garums += len(r)
    izvade({**atsauce(ak, v), "teksts": "\n".join(rindas),
            **({"apgriezts": f"turpinājums: teksts {a.lokators} --no {turpinat}"} if turpinat else {})})


# ------------------------------------------------------------------ atsauce
def cmd_atsauce(c, a):
    out = []
    for lok in a.lokatori:
        try:
            ak = Akts(c, akta_id(lok))
            out.append(atsauce(ak, ak.atrast(lok)))
        except LookupError as e:
            out.append({"lokators": lok, "kluda": str(e)})
    izvade(out)


# ------------------------------------------------------------------ saistitie
def cmd_saistitie(c, a):
    lid = a.id
    kes: dict = {}
    if c.execute("SELECT 1 FROM akti WHERE likumi_id=?", (lid,)).fetchone() is None:
        kluda(f"akts {lid} nav datubāzē")
    out = {"akts": akta_rinda(c, lid, kes)}
    for nos in (SAITES if a.veids == "visi" else [a.veids]):
        kods, apr = SAITES[nos]
        ids = [r[0] for r in c.execute(
            """SELECT DISTINCT t.uz_id FROM attiecibas t LEFT JOIN akti a ON a.likumi_id = t.uz_id
               WHERE t.no_id=? AND t.kods=? ORDER BY a.pienemts DESC, t.uz_id DESC""", (lid, kods))]
        rindas = [akta_rinda(c, i, kes) for i in ids]
        if a.statuss == "speka":
            rindas = [r for r in rindas if r.get("statuss") == "spēkā esošs"]
        if not a.grozijumi and nos in ("izdoti", "pamats", "atcel"):
            rindas = [r for r in rindas if not re.match(r'^(.*")?(Par )?[Gg]rozījum', r.get("atsauce", "").split('"', 1)[-1])]
        if not ids:
            continue
        out[nos] = {"nozime": apr, "skaits": len(rindas),
                    "akti": rindas[:a.limits],
                    **({"apgriezts": f"parādīti {a.limits}; --limits N"} if len(rindas) > a.limits else {})}
    out["piezime"] = ("Sakarības rekonstruētas no aktu satura: groza/atceļ/izdots saskaņā ar "
                      "ir ~95% precīzas; pārbaudi svarīgās likumi.lv cilnē 'Saistītie dokumenti'.")
    izvade(out)


# ------------------------------------------------------------------ atsauces (saites tekstā)
def cmd_atsauces(c, a):
    ak, v = ielade(c, a.lokators)
    kes: dict = {}
    if a.izejosas:
        ids = list(ak.V) if v is None else [v["id"]] + ak.apaksvienibas(v["id"])
        rindas = []
        for i in range(0, len(ids), 500):
            gab = ids[i:i + 500]
            rindas += c.execute(
                f"""SELECT no_vienibas, uz_likumi_id, uz_enkurs, veids, teksts FROM atsauces
                    WHERE likumi_id=? AND no_vienibas IN ({','.join('?' * len(gab))}) AND veids <> 'grozijums'""",
                [ak.id] + gab).fetchall()
        grupas: dict[tuple, dict] = {}
        for r in rindas:
            g = grupas.setdefault((r["uz_likumi_id"], r["uz_enkurs"]), {"no": [], "veids": r["veids"]})
            lok = ak.lokators(r["no_vienibas"])
            if lok not in g["no"]:
                g["no"].append(lok)
        out = []
        merki: dict[int, Akts | None] = {}
        for (uz, enk), g in sorted(grupas.items(), key=lambda kv: -len(kv[1]["no"])):
            if uz not in merki:
                try:
                    merki[uz] = Akts(c, uz) if len(merki) < 200 else None
                except LookupError:
                    merki[uz] = None
            m = merki[uz]
            if m is not None and enk and enk in m.pec_enkura:
                at = atsauce(m, m.V[m.pec_enkura[enk]])
            else:
                at = dict(akta_rinda(c, uz, kes))
                if enk and "url" in at:
                    at["url"] += "#" + enk
            out.append({"uz": {k: at.get(k) for k in ("lokators", "likumi_id", "atsauce", "url", "statuss") if at.get(k)},
                        "veids": g["veids"], "no_vienibam": g["no"][:10]})
        izvade({**atsauce(ak, v), "virziens": "izejošās: uz ko atsaucas šis akts / vienība",
                "skaits": len(out), "atsauces": out[:a.limits]})
        return
    # ienākošās
    enk = None
    par = [ak.id]
    sql = "SELECT s.likumi_id, s.no_vienibas, s.veids, s.uz_enkurs FROM atsauces s JOIN akti a ON a.likumi_id=s.likumi_id " \
          "WHERE s.uz_likumi_id=? AND s.likumi_id<>s.uz_likumi_id AND s.veids IN ('atsauce','izdots_saskana_ar')"
    if v is not None:
        enk = next((x["enkurs"] for x in reversed(ak.kede(v["id"])) if x["enkurs"]), None)
        if not enk:
            kluda("vienībai nav likumi.lv enkura: ienākošās atsauces var meklēt tikai aktam vai pantam/punktam ar enkuru")
        sql += " AND s.uz_enkurs=?"
        par.append(enk)
    if a.statuss == "speka":
        sql += " AND a.statuss='spēkā esošs'"
    if not a.grozijumi:
        sql += f" AND NOT {GROZ_SQL}"
    grupas: dict[int, dict] = {}
    for r in c.execute(sql, par):
        g = grupas.setdefault(r["likumi_id"], {"n": 0, "vien": [], "veidi": set(), "panti": {}})
        g["n"] += 1
        g["veidi"].add(r["veids"])
        if r["uz_enkurs"]:
            g["panti"][r["uz_enkurs"]] = g["panti"].get(r["uz_enkurs"], 0) + 1
        if len(g["vien"]) < a.vienibas and r["no_vienibas"]:
            g["vien"].append(r["no_vienibas"])
    out = []
    for lid, g in sorted(grupas.items(), key=lambda kv: -kv[1]["n"])[:a.limits]:
        r = dict(akta_rinda(c, lid, kes))
        r["atsaucu_skaits"] = g["n"]
        r["veidi"] = sorted(g["veidi"])
        if v is None and g["panti"]:
            r["uz_enkuriem"] = dict(sorted(g["panti"].items(), key=lambda kv: -kv[1])[:8])
        if g["vien"]:
            no = Akts(c, lid)
            r["no_vienibam"] = [{k: x[k] for k in ("lokators", "atsauce", "url")}
                                for x in (atsauce(no, no.V[i]) for i in g["vien"] if i in no.V)]
        out.append(r)
    izvade({**atsauce(ak, v), "virziens": "ienākošās: kuri akti tekstā atsaucas uz šo aktu / vienību",
            "enkurs": enk, "aktu_skaits": len(grupas), "paraditi": len(out), "akti": out,
            "piezime": "Tikai atsauces, kas likumi.lv tekstā ir saites; ap 60% norāda konkrētu pantu/punktu."})


# ------------------------------------------------------------------ atrisinat
def cmd_atrisinat(c, a):
    from teksta_atsauces import Atrisinatajs
    c.row_factory = None
    r = Atrisinatajs(c)
    atrasts = r.atrast(" ".join(a.teksts), a.datums, citi=True)
    c.row_factory = sqlite3.Row
    out = []
    for lid, enk, fragm in atrasts:
        ak = Akts(c, lid)
        v = ak.V[ak.pec_enkura[enk]] if enk and enk in ak.pec_enkura else None
        x = {"atrasts_teksta": fragm, **atsauce(ak, v)}
        if enk and v is None:
            x.setdefault("piezimes", []).append(f"tekstā minētais pants ({enk}) aktā nav atrasts: atsauce ir uz visu aktu")
        out.append(x)
    izvade({"teksts": " ".join(a.teksts), "datums": a.datums, "atsauces": out,
            "piezime": "Atpazīst likumu nosaukumus locījumos un 'Ministru kabineta <datums> noteikumi Nr. N'; "
                       "daļu un punktu tekstā neatrisina (tikai pantu). Vairākiem aktiem ar vienādu nosaukumu izvēlas "
                       "to, kas bija spēkā --datums dienā (noklusēti: jaunāko)."})


# ------------------------------------------------------------------ sql / statuss
def cmd_sql(c, a):
    q = a.vaicajums.strip().rstrip(";")
    if not re.match(r"^(select|with|explain|pragma table_info)\b", q, re.I):
        kluda("atļauti tikai SELECT / WITH vaicājumi")
    try:
        cur = c.execute(q)
        rindas = cur.fetchmany(a.limits + 1)
    except sqlite3.Error as e:
        kluda(f"SQL kļūda: {e}")
    izvade({"kolonnas": [d[0] for d in cur.description or []], "rindas": [list(r) for r in rindas[:a.limits]],
            **({"apgriezts": f"vairāk par {a.limits} rindām; --limits N"} if len(rindas) > a.limits else {})})


def cmd_statuss(c, a):
    r = c.execute("SELECT COUNT(*), MIN(lejupieladets), MAX(lejupieladets), MAX(parsera_versija) FROM akti").fetchone()
    izvade({"akti": r[0], "lejupieladets_no": r[1], "lejupieladets_lidz": r[2], "parsera_versija": r[3],
            "pec_statusa": {x[0] or "(nav)": x[1] for x in c.execute("SELECT statuss, COUNT(*) FROM akti GROUP BY 1")},
            "speka_esosi_pamatakti": {x[0]: x[1] for x in c.execute(
                f"SELECT a.veids, COUNT(*) FROM akti a WHERE a.statuss='spēkā esošs' AND NOT {GROZ_SQL} "
                "GROUP BY 1 ORDER BY 2 DESC LIMIT 8")},
            "attiecibas": c.execute("SELECT COUNT(*) FROM attiecibas").fetchone()[0],
            "piezime": "Teksts ir akta spēkā esošā redakcija lejupielādes dienā; vēsturisko redakciju tekstu nav."})


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)

    def kopigie(p, groz_palidziba="iekļaut arī grozījumu aktus"):
        p.add_argument("--statuss", choices=["speka", "visi", "zaudejis"], default="speka",
                       help="noklusēti tikai spēkā esošie akti")
        p.add_argument("--grozijumi", action="store_true", help=groz_palidziba)
        p.add_argument("--limits", type=int, default=20)

    p = sp.add_parser("meklet", help="meklēt aktus pēc teksta un nosaukuma")
    p.add_argument("vaicajums", nargs="+", help="vārdi (visi obligāti; galotnes tiek ignorētas) vai FTS5 sintakse")
    p.add_argument("--nosaukuma", action="store_true", help="meklēt tikai aktu nosaukumos")
    p.add_argument("--veids", help="likums | noteikumi | rīkojums | saistošie noteikumi | ... (SQL LIKE)")
    p.add_argument("--izdevejs", help="piem. 'Ministru kabinets', 'Saeima', '%%dome' (SQL LIKE)")
    p.add_argument("--tema", help="likumi.lv tēmas daļa (tēmas ir tikai ~12%% aktu)")
    p.add_argument("--vienibas", type=int, default=3, help="cik atrastās vienības rādīt katram aktam")
    kopigie(p)
    p.set_defaults(f=cmd_meklet)

    p = sp.add_parser("konteksts", help="RAG: jautājumam atbilstošākās normas ar pilnu tekstu un atsauci")
    p.add_argument("vaicajums", nargs="+", help="atslēgvārdi (galotnes tiek ignorētas) vai FTS5 sintakse")
    p.add_argument("--akts", type=int, help="meklēt tikai šajā aktā (likumi_id)")
    p.add_argument("--veids", help="likums | noteikumi | ... (SQL LIKE)")
    p.add_argument("--izdevejs", help="piem. 'Ministru kabinets' (SQL LIKE)")
    p.add_argument("--tema", help="likumi.lv tēmas daļa")
    p.add_argument("--uz-aktu", type=int, default=3, dest="uz_aktu", help="maksimālais fragmentu skaits no viena akta")
    p.add_argument("--garums", type=int, default=1500, help="fragmenta maksimālais garums rakstzīmēs")
    kopigie(p)
    p.set_defaults(f=cmd_konteksts, limits=8)

    p = sp.add_parser("akts", help="akta pase, saturs un sakarību skaits")
    p.add_argument("id", type=int)
    p.add_argument("--saturs-limits", type=int, default=150)
    p.set_defaults(f=cmd_akts)

    p = sp.add_parser("teksts", help="akta vai vienības teksts ar lokatoriem")
    p.add_argument("lokators")
    p.add_argument("--no", help="sākt no šīs vienības (turpinājumam)")
    p.add_argument("--limits", type=int, default=12000, help="maksimālais rakstzīmju skaits")
    p.add_argument("--viss", action="store_true", help="bez apjoma ierobežojuma")
    p.add_argument("--labojumi", action="store_true", help="rādīt grozījumu piezīmes")
    p.set_defaults(f=cmd_teksts)

    p = sp.add_parser("atsauce", help="gatava atsauce ar likumi.lv saiti")
    p.add_argument("lokatori", nargs="+")
    p.set_defaults(f=cmd_atsauce)

    p = sp.add_parser("saistitie", help="akta sakarības: groza, atceļ, izdots saskaņā ar")
    p.add_argument("id", type=int)
    p.add_argument("--veids", choices=[*SAITES, "visi"], default="visi")
    kopigie(p, "iekļaut grozījumu aktus sarakstos izdoti / pamats / atcel")
    p.set_defaults(f=cmd_saistitie, statuss="visi")

    p = sp.add_parser("atsauces", help="saites tekstā: kas atsaucas uz aktu/pantu vai uz ko atsaucas tas")
    p.add_argument("lokators")
    p.add_argument("--izejosas", action="store_true", help="uz ko atsaucas šis akts / vienība (noklusēti: ienākošās)")
    p.add_argument("--vienibas", type=int, default=3)
    kopigie(p)
    p.set_defaults(f=cmd_atsauces)

    p = sp.add_parser("atrisinat", help="atsauce brīvā tekstā -> akts un pants")
    p.add_argument("teksts", nargs="+")
    p.add_argument("--datums", help="GGGG-MM-DD: kurā dienā atsauce rakstīta")
    p.set_defaults(f=cmd_atrisinat)

    p = sp.add_parser("sql", help="SELECT vaicājums (tikai lasīšana)")
    p.add_argument("vaicajums")
    p.add_argument("--limits", type=int, default=200)
    p.set_defaults(f=cmd_sql)

    p = sp.add_parser("statuss", help="datu apjoms un svaigums")
    p.set_defaults(f=cmd_statuss)

    a = ap.parse_args()
    c = savienot()
    a.f(c, a)


if __name__ == "__main__":
    main()
