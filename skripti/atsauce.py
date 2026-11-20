"""Atsauces uz tiesību aktiem un to vienībām: lokators <-> vienība, atsauces teksts, likumi.lv saite.

Lokators ir stabila vienības adrese (vienibas.id mainās katrā pārparsēšanā, lokators nemainās):
  5138              viss akts
  5138#p2           vienība ar likumi.lv enkuru (pants, MK noteikumu punkts, nodaļa n2, pārejas noteikumi pn1, pielikums)
  5138#p2/4/1       no enkura uz leju pēc numuriem: 2. panta ceturtās daļas 1. punkts
  330033/3/1/2      akts bez enkuriem (vecais formāts): 3. panta pirmās daļas 2. punkts
  330033~17         vienība bez numura: kārtas numurs aktā (seciba); nav stabils starp akta redakcijām

  from atsauce import Akts, atsauce
  a = Akts(c, 5138); v = a.atrast("5138#p2/4/1"); atsauce(a, v)
  -> {"atsauce": "Autortiesību likuma 2. panta ceturtās daļas 1. punkts", "url": "https://likumi.lv/ta/id/5138#p2", ...}
"""
from __future__ import annotations

import re
import sqlite3

URL = "https://likumi.lv/ta/id/{}"
SUP = "⁰¹²³⁴⁵⁶⁷⁸⁹"
STRUKT = ("pants", "dala", "punkts", "apakspunkts", "parejas", "pielikums")
VIRSR = ("nodala", "apaksnodala", "dala_akta", "virsraksts")
KARTAS = ["", "pirmā", "otrā", "trešā", "ceturtā", "piektā", "sestā", "septītā", "astotā", "devītā", "desmitā",
          "vienpadsmitā", "divpadsmitā", "trīspadsmitā", "četrpadsmitā", "piecpadsmitā", "sešpadsmitā",
          "septiņpadsmitā", "astoņpadsmitā", "deviņpadsmitā", "divdesmitā"]
MENESI = ["", "janvāra", "februāra", "marta", "aprīļa", "maija", "jūnija", "jūlija", "augusta", "septembra",
          "oktobra", "novembra", "decembra"]
VEIDS_GEN = {"likums": "likuma", "noteikumi": "noteikumu", "rīkojums": "rīkojuma", "instrukcija": "instrukcijas",
             "lēmums": "lēmuma", "saistošie noteikumi": "saistošo noteikumu", "spriedums": "sprieduma",
             "ieteikumi": "ieteikumu", "nolikums": "nolikuma", "paziņojums": "paziņojuma", "kārtība": "kārtības",
             "protokols": "protokola", "plāns": "plāna", "informācija": "informācijas"}
RE_GROZ = re.compile(r"^(Par\s+)?grozījum", re.I)
RE_LOK = re.compile(r"^(\d+)(?:#([\w\-]+))?((?:/[^/]+)*)/?$")
RE_LOK_SEC = re.compile(r"^(\d+)~(\d+)$")


def gada_datums(d: str | None) -> str | None:
    """'2020-07-14' -> '2020. gada 14. jūlija'"""
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", d or "")
    return f"{m.group(1)}. gada {int(m.group(3))}. {MENESI[int(m.group(2))]}" if m and 1 <= int(m.group(2)) <= 12 else None


def izdeveja_gen(izd: str | None) -> str | None:
    """'Ministru kabinets' -> 'Ministru kabineta'. Loka tikai pēdējo vārdu; ja nav droši, atgriež None."""
    if not izd:
        return None
    if re.search(r'[/"\-]', izd):
        return None
    galv, _, ped = izd.rpartition(" ")
    for no, uz in (("ija", "ijas"), ("ts", "ta"), ("js", "ja"), ("rs", "ra"), ("ns", "na"), ("ms", "ma"),
                   ("ls", "la"), ("ds", "da"), ("ks", "ka"), ("e", "es"), ("a", "as")):
        if ped.endswith(no) and len(ped) > len(no) + 1:
            siev = uz.endswith("s")
            # saskaņotie īpašības vārdi: Centrālā -> Centrālās (siev.), Nacionālais -> Nacionālā (vīr.)
            vardi = [(w + "s" if siev and w.endswith("ā") else w[:-3] + "ā" if not siev and w.endswith("ais") else w)
                     for w in galv.split()]
            return " ".join(vardi + [ped[: -len(no)] + uz])
    return None


def nr(n: str) -> str:
    """'16' -> '16.', '43¹' -> '43.¹', '5.4¹' -> '5.4.¹' (iespraustās vienības apzīmējums ar augšrakstu)"""
    m = re.match(rf"^(.*?)([{SUP}]+)$", n)
    return f"{m.group(1)}.{m.group(2)}" if m else f"{n}."


def bez_sup(n: str) -> str:
    return re.sub(rf"[{SUP}]+", "", n or "")


class Akts:
    """Viena akta pase un vienību koks atmiņā."""

    def __init__(self, c: sqlite3.Connection, lid: int):
        c.row_factory = sqlite3.Row
        r = c.execute("SELECT * FROM akti WHERE likumi_id=?", (lid,)).fetchone()
        if r is None:
            raise LookupError(f"akts {lid} nav datubāzē")
        self.pase = dict(r)
        self.id = lid
        self.V = {x["id"]: dict(x) for x in c.execute(
            """SELECT id, parent_id, tips, numurs, enkurs, limenis, virsraksts, teksts, labojumi, tiesu_atzinas, seciba
               FROM vienibas WHERE likumi_id=? ORDER BY seciba""", (lid,))}
        self.berni: dict[int | None, list[int]] = {}
        for v in self.V.values():
            self.berni.setdefault(v["parent_id"], []).append(v["id"])
        self.pec_enkura: dict[str, int] = {}
        self.pec_secibas = {v["seciba"]: v["id"] for v in self.V.values()}
        for v in self.V.values():
            if v["enkurs"]:
                self.pec_enkura.setdefault(v["enkurs"], v["id"])
        red = c.execute("SELECT no FROM redakcijas WHERE likumi_id=? AND tips='Spēkā esošā' ORDER BY no DESC",
                        (lid,)).fetchone()
        self.redakcija_no = red[0] if red else None

    # ---------------------------------------------------------------- koks
    def kede(self, vid: int) -> list[dict]:
        """Vienība un tās priekšteči, no saknes uz leju."""
        out = []
        while vid is not None and vid in self.V:
            out.append(self.V[vid])
            vid = self.V[vid]["parent_id"]
        return out[::-1]

    def apaksvienibas(self, vid: int) -> list[int]:
        out = []
        for b in self.berni.get(vid, []):
            out.append(b)
            out += self.apaksvienibas(b)
        return out

    def _berns(self, vid: int | None, num: str) -> int | None:
        for b in self.berni.get(vid, []):
            if self.V[b]["numurs"] == num and self.V[b]["tips"] in STRUKT:
                return b
        return None

    def _augsejais(self, num: str) -> int | None:
        """Pirmā numurētā strukturālā vienība, kurai virs sevis ir tikai virsraksti (akts bez enkuriem)."""
        for v in self.V.values():
            if v["numurs"] == num and v["tips"] in STRUKT and all(
                    x["tips"] not in STRUKT for x in self.kede(v["id"])[:-1]):
                return v["id"]
        return None

    # ---------------------------------------------------------------- lokators
    def atrast(self, lok: str) -> dict | None:
        """Lokators -> vienība (dict) vai None, ja lokators norāda uz visu aktu. Met LookupError, ja nav."""
        m = RE_LOK_SEC.match(lok)
        if m:
            vid = self.pec_secibas.get(int(m.group(2)))
            if vid is None:
                raise LookupError(f"{lok}: aktā nav vienības ar kārtas numuru {m.group(2)}")
            return self.V[vid]
        m = RE_LOK.match(lok)
        if not m or int(m.group(1)) != self.id:
            raise LookupError(f"{lok}: nederīgs lokators")
        # ASCII pieraksts augšrakstam: 4.7^1 = 4.7¹
        enk, cels = m.group(2), [re.sub(r"\^(\d+)", lambda g: g.group(1).translate(str.maketrans("0123456789", SUP)), x)
                                 for x in m.group(3).split("/") if x]
        if not enk and not cels:
            return None
        if enk:
            vid = self.pec_enkura.get(enk)
            if vid is None:
                raise LookupError(f"{lok}: aktā nav enkura #{enk}")
        else:
            vid = self._augsejais(cels[0])
            if vid is None:
                raise LookupError(f"{lok}: aktā nav vienības ar numuru {cels[0]}")
            cels = cels[1:]
        for num in cels:
            b = self._berns(vid, num)
            if b is None:
                raise LookupError(f"{lok}: vienībai nav apakšvienības ar numuru {num}")
            vid = b
        return self.V[vid]

    def lokators(self, vid: int | None) -> str:
        if vid is None:
            return str(self.id)
        k = self.kede(vid)
        lok = None
        for i in range(len(k) - 1, -1, -1):  # tuvākais priekštecis ar enkuru
            if k[i]["enkurs"]:
                atl = k[i + 1:]
                if all(x["numurs"] and x["tips"] in STRUKT for x in atl):
                    lok = f"{self.id}#{k[i]['enkurs']}" + "".join("/" + x["numurs"] for x in atl)
                break
        else:
            s = [x for x in k if x["tips"] in STRUKT]
            if s and s[-1] is k[-1] and all(x["numurs"] for x in s) and "/" not in "".join(x["numurs"] for x in s):
                lok = f"{self.id}/" + "/".join(x["numurs"] for x in s)
        if lok:
            try:
                r = self.atrast(lok)
                if r is not None and r["id"] == vid:
                    return lok
            except LookupError:
                pass
        return f"{self.id}~{self.V[vid]['seciba']}"

    # ---------------------------------------------------------------- nosaukums
    def nosaukums_atsaucei(self) -> tuple[str, bool]:
        """(akta apzīmējums, vai ir ģenitīvā). Ģenitīvs ļauj rakstīt 'X likuma 5. pants'; citādi 'X, 5. pants'."""
        p = self.pase
        nos = (p["nosaukums"] or "").strip() or f"akts Nr. {self.id}"
        veids, dat = p["veids"], gada_datums(p["pienemts"])
        if veids == "likums" and not RE_GROZ.match(nos):
            if nos.startswith("Par "):
                return f'likuma "{nos}"', True
            if re.match(r"^Civillikums\b", nos):
                return "Civillikuma", True
            if not re.search(r"\.\s+[A-ZĀČĒĢĪĶĻŅŠŪŽ]", nos):
                for no, uz in (("likums", "likuma"), ("kodekss", "kodeksa"), ("Satversme", "Satversmes"),
                               ("rullis", "ruļļa"), ("reglaments", "reglamenta")):
                    if nos.endswith(no):
                        return nos[: -len(no)] + uz, True
            return nos, False
        izd = izdeveja_gen(p["izdevejs"])
        vg = VEIDS_GEN.get(veids or "")
        num = f" Nr. {p['numurs']}" if p["numurs"] else ""
        if veids == "likums" and dat:
            return f'{dat} likuma "{nos}"', True
        if izd and dat and vg:
            return f'{izd} {dat} {vg}{num} "{nos}"', True
        dalas = [x for x in (p["izdevejs"], f"{veids or 'akts'}{num}", p["pienemts"]) if x]
        return f'"{nos}" ({", ".join(dalas)})', False

    def nosaukums_nom(self) -> str:
        """Akta apzīmējums nominatīvā (saraksta ierakstam vai atsaucei uz visu aktu)."""
        p = self.pase
        nos = (p["nosaukums"] or "").strip() or f"akts Nr. {self.id}"
        veids, dat = p["veids"], gada_datums(p["pienemts"])
        if veids == "likums" and not RE_GROZ.match(nos):
            return f'likums "{nos}"' if nos.startswith("Par ") else nos
        izd = izdeveja_gen(p["izdevejs"])
        num = f" Nr. {p['numurs']}" if p["numurs"] else ""
        if veids == "likums" and dat:  # grozījumu likums: bez izdevēja
            return f'{dat} likums "{nos}"'
        if izd and dat and veids:
            return f'{izd} {dat} {veids}{num} "{nos}"'
        return self.nosaukums_atsaucei()[0]


def vienibas_cels(a: Akts, v: dict) -> tuple[str, list[str]]:
    """Vienības adrese akta iekšienē: '2. panta ceturtās daļas 1. punkts'. Atgriež (teksts, piezīmes)."""
    piez: list[str] = []
    if v["tips"] in VIRSR:
        vards = {"nodala": "nodaļa", "apaksnodala": "apakšnodaļa", "dala_akta": "daļa"}.get(v["tips"])
        if vards and v["numurs"]:
            return f"{v['numurs']}{'.' if v['numurs'].isdigit() else ''} {vards}", piez
        return (f'sadaļa "{v["virsraksts"]}"' if v["virsraksts"] else ""), piez
    k = [x for x in a.kede(v["id"]) if x["tips"] in STRUKT]
    if not k or k[-1] is not v:
        nos = {"galvene": "ievaddaļa", "izdots_saskana_ar": "izdošanas pamats", "es_atsauce":
               "informatīvā atsauce uz Eiropas Savienības tiesību aktiem"}.get(v["tips"], "")
        if k:  # teksts zem pielikuma u.tml.: citē tuvāko strukturālo vienību
            t, piez = vienibas_cels(a, k[-1])
            return t, piez + ["vienībai nav sava numura: norādīta tuvākā numurētā vienība"]
        return nos, piez
    # pilns hierarhisks numurs (4.1.1) jau ietver vecākpunktus
    atl = []
    for i, x in enumerate(k):
        n = bez_sup(x["numurs"] or "")
        if x["tips"] in ("punkts", "apakspunkts") and any(
                y["tips"] in ("punkts", "apakspunkts") and bez_sup(y["numurs"] or "").startswith(n + ".")
                for y in k[i + 1:]):
            continue
        atl.append(x)
    dalas = []
    for i, x in enumerate(atl):
        ped = i == len(atl) - 1
        n, t = x["numurs"], x["tips"]
        if not n:
            if t == "pielikums":
                dalas.append("pielikums" if ped else "pielikuma")
            else:
                piez.append(f"vienībai ({t}) nav numura: adrese nav pilnīga")
            continue
        if t == "pants":
            dalas.append(f"{nr(n)} {'pants' if ped else 'panta'}")
        elif t == "dala":
            if n.isascii() and n.isdigit() and 0 < int(n) < len(KARTAS):
                dalas.append(f"{KARTAS[int(n)] if ped else KARTAS[int(n)][:-1] + 'ās'} {'daļa' if ped else 'daļas'}")
            else:
                dalas.append(f"{nr(n)} {'daļa' if ped else 'daļas'}")
        elif t == "parejas":
            dalas.append(f"pārejas noteikumu {nr(n)} {'punkts' if ped else 'punkta'}")
        elif t == "pielikums":
            dalas.append(f"{nr(n)} {'pielikums' if ped else 'pielikuma'}")
        elif t == "punkts":
            dalas.append(f"{nr(n)} {'punkts' if ped else 'punkta'}")
        else:
            vards = "apakšpunkts" if ped else "apakšpunkta"
            dalas.append(f'"{n}" {vards}' if n.isalpha() else f"{nr(n)} {vards}")
    return " ".join(dalas), piez


def atsauce(a: Akts, v: dict | None) -> dict:
    """Gatava atsauce uz aktu (v=None) vai vienību: teksts, likumi.lv saite, Markdown, statuss, piezīmes."""
    p = a.pase
    piez: list[str] = []
    url = URL.format(a.id)
    enk = None
    if v is None:
        teksts = a.nosaukums_nom()
    else:
        cels, piez = vienibas_cels(a, v)
        nos, gen = a.nosaukums_atsaucei()
        if not cels:
            teksts = a.nosaukums_nom()
            if v["tips"] != "nosaukums":
                piez.append("vienībai nav citējamas adreses: atsauce ir uz visu aktu")
        elif gen:
            teksts = f"{nos} {cels}"
        else:
            teksts = f"{nos}, {cels}"
        for x in reversed(a.kede(v["id"])):
            if x["enkurs"]:
                enk = x["enkurs"]
                if x is not v and x["tips"] in VIRSR:
                    piez.append("saite ved uz nodaļu, kurā ir vienība (pašai vienībai likumi.lv enkura nav)")
                break
        if enk:
            url += "#" + enk
        else:
            piez.append("likumi.lv šai vienībai nav enkura: saite ved uz akta sākumu")
        if re.match(r"^\((izslēgt|svītrot|zaudēj)", (v["teksts"] or "").lower()):
            piez.append("vienība ir izslēgta")
    if p["statuss"] and p["statuss"] != "spēkā esošs":
        piez.append(f"akta statuss: {p['statuss']}" + (f" ({p['zaude_speku']})" if p["zaude_speku"] else ""))
    return {
        "lokators": a.lokators(v["id"] if v else None),
        "atsauce": teksts,
        "url": url,
        "markdown": f"[{teksts}]({url})",
        "statuss": p["statuss"],
        "redakcija_no": a.redakcija_no,
        "dati_uz": (p["lejupieladets"] or "")[:10] or None,
        **({"piezimes": piez} if piez else {}),
    }
