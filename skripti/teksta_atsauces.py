"""Teksta atsauču atrisinātājs: latviešu tiesību akta nosaukums tekstā -> likumi_id (bez HTML saites).

Atpazīst:
  - "Valsts pārvaldes iekārtas likuma 16.panta"  (likuma/likumā/likumu/likumam -> likums)
  - 'likumā "Par valsts un pašvaldību mantas atsavināšanu"'
  - "Ministru kabineta 2005. gada 20. septembra noteikumos Nr. 716"  (izdevējs + datums + numurs)
Vairākiem aktiem ar vienādu nosaukumu izvēlas to, kas bija spēkā atsauces datumā.

  from teksta_atsauces import Atrisinatajs
  r = Atrisinatajs(sqlite_conn)
  r.atrast("Izdoti saskaņā ar Ministru kabineta iekārtas likuma 15.panta otro daļu", "2003-05-01")
  -> [(59281, 'p15', 'Ministru kabineta iekārtas likuma 15.panta')]
"""
import re
from collections import defaultdict

MENESI = {"janvāra": 1, "februāra": 2, "marta": 3, "aprīļa": 4, "maija": 5, "jūnija": 6, "jūlija": 7,
          "augusta": 8, "septembra": 9, "oktobra": 10, "novembra": 11, "decembra": 12}
PEDINAS = '"“”„«»\''
RE_LIKUMS = re.compile(r"((?:[A-ZĀČĒĢĪĶĻŅŠŪŽ][\w\-]*\s+|[a-zāčēģīķļņšūž][\w\-]*\s+|un\s+){0,10}?)likum(?:a|ā|u|am|s)\b"
                       r"(?:\s+[" + PEDINAS + r"]([^" + PEDINAS + r"]{3,200})[" + PEDINAS + r"])?")
RE_PANTS = re.compile(r"^\s*(?:\(?[^)]{0,40}\)\s*)?(\d+)\.?\s*(?:<sup>)?([\d⁰¹²³⁴⁵⁶⁷⁸⁹]+)?(?:</sup>)?\s*\.?\s*pant", re.I)
RE_MK = re.compile(r"(Ministru kabineta|Ministru Kabineta)\s+(\d{4})\.\s*gada\s+(\d{1,2})\.\s*(" +
                   "|".join(MENESI) + r")\s+(noteikum\w*|rīkojum\w*|instrukcij\w*)\s+Nr\.\s*(\d+)", re.I)
# citu izdevēju (pašvaldību, iestāžu) akti: "<izdevējs> 2024. gada 23. maija saistošajos noteikumos Nr. 13"
RE_CITI = re.compile(r"(?:(?P<g>\d{4})\.\s*gada\s+(?P<d>\d{1,2})\.\s*(?P<m>" + "|".join(MENESI) +
                     r")|(?P<d2>\d{1,2})\.(?P<m2>\d{1,2})\.(?P<g2>\d{4})\.?)"
                     r"(?P<starp>(?:\s+[\w\-]+){0,5}?)\s+"     # izdevējs mēdz būt arī starp datumu un akta veidu
                     r"(?:saistošaj\w+\s+noteikum\w*|noteikum\w*|nolikum\w*|instrukcij\w*|lēmum\w*|rīkojum\w*)"
                     r"\s+Nr\.\s*(?P<nr>[\w/\-.–]*\w)", re.I)
RE_SALIKTS = re.compile(r"\b(\w{3,}likum)(?:a|ā|u|am|s)\b", re.I)    # Krimināllikuma, Komerclikumā
MK_VEIDI = {"noteikum": "noteikumi", "rīkojum": "rīkojums", "instrukcij": "instrukcija"}


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(f"[{PEDINAS}]", "", s or "")).strip().lower()


class Atrisinatajs:
    def __init__(self, c):
        self.vardi = defaultdict(list)    # normalizēts nosaukuma "stumbrs" -> [(id, pienemts, zaude_speku)]
        self.mk = defaultdict(list)       # (veids, datums, numurs) -> [id]
        self.citi = defaultdict(list)     # (datums, numurs) -> [(id, izdevējs, nosaukums)] ne-MK akti
        for lid, nos, izd, veids, pien, zaud, num in c.execute(
                "SELECT likumi_id, nosaukums, izdevejs, veids, pienemts, zaude_speku, numurs FROM akti "
                "WHERE nosaukums IS NOT NULL"):
            if veids == "likums" or (nos and nos.endswith(" likums")):
                n = norm(nos)
                if " " not in n and n.endswith("likums") and n != "likums":
                    self.vardi["#" + n[:-1]].append((lid, pien, zaud))   # salikteņi: krimināllikum
                elif n.endswith(" likums"):
                    self.vardi[n[:-len(" likums")]].append((lid, pien, zaud))
                elif n.startswith("par ") or veids == "likums":
                    self.vardi["@" + n].append((lid, pien, zaud))   # likums "Par ..."
            if izd == "Ministru kabinets" and num and pien:
                self.mk[(veids, pien, num.strip())].append(lid)
            elif izd and num and pien and veids != "likums":
                self.citi[(pien, num.strip().lower().replace("–", "-"))].append((lid, izd, norm(nos)))
        for v in self.vardi.values():
            v.sort(key=lambda x: x[1] or "")

    def _izvele(self, kandidati, datums):
        if not kandidati:
            return None
        if datums:
            speka = [k for k in kandidati if (k[1] or "") <= datums and (not k[2] or k[2] > datums)]
            if speka:
                return speka[-1][0]
            agrak = [k for k in kandidati if (k[1] or "") <= datums]
            if agrak:
                return agrak[-1][0]
        return kandidati[-1][0]

    def likums(self, priekstteksts: str, citats: str | None, datums: str | None):
        """priekstteksts = vārdi pirms 'likuma'; mēģina garāko sakritību, nometot vārdus no kreisās puses."""
        if citats:
            k = self.vardi.get("@" + norm(citats))
            if k:
                return self._izvele(k, datums)
        # visas sakritības (garākā "Latvijas Republikas izglītības" un īsākā "izglītības") -> izvēle pēc datuma
        vardi = norm(priekstteksts).split()
        kand = []
        for i in range(len(vardi)):
            kand += self.vardi.get(" ".join(vardi[i:]), [])
        return self._izvele(sorted(set(kand), key=lambda x: x[1] or ""), datums)

    def cits(self, m, teksts: str):
        """Pašvaldības vai iestādes akts pēc datuma un numura. Vairāki izdevēji mēdz izdot aktu ar to pašu datumu un
        numuru, tāpēc kandidātam jāatbilst arī izdevējam (vietvārda celms pirms datuma) vai nosaukumam pēdiņās."""
        if m.group("g"):
            d = f"{m.group('g')}-{MENESI[m.group('m').lower()]:02d}-{int(m.group('d')):02d}"
        else:
            d = f"{m.group('g2')}-{int(m.group('m2')):02d}-{int(m.group('d2')):02d}"
        kand = self.citi.get((d, m.group("nr").lower().replace("–", "-")), [])
        if not kand:
            return None
        pirms = norm(teksts[max(0, m.start() - 120):m.start()])
        if pirms.endswith("ministru kabineta"):
            return None
        pirms += " " + norm(m.group("starp"))
        cm = re.match(r"\s*[" + PEDINAS + r"]([^" + PEDINAS + r"]{5,})", teksts[m.end():])
        citats = norm(cm.group(1)) if cm else ""
        labie = []
        for lid, izd, nos in kand:
            celms = norm(izd).split()[0]
            celms = celms[:-2] if len(celms) > 5 else celms[:-1]
            p_izd = bool(re.search(r"\b" + re.escape(celms), pirms))
            p_nos = bool(citats) and (nos.startswith(citats[:60]) or citats.startswith(nos[:60]))
            if p_izd or p_nos:
                labie.append((p_izd + p_nos, not nos.startswith(("groz", "par groz")), lid))
        if not labie:
            return None
        labie.sort(reverse=True)
        if len(labie) > 1 and labie[0][:2] == labie[1][:2]:
            return None    # nav viennozīmīgs
        return labie[0][2]

    def atrast(self, teksts: str, datums: str | None = None, citi: bool = False):
        """-> [(likumi_id, enkurs | None, atrastais teksts)]. citi=True: arī pašvaldību un iestāžu akti pēc
        datuma un numura (saistošie noteikumi u.c.)."""
        out = []
        if citi:
            for m in RE_CITI.finditer(teksts or ""):
                lid = self.cits(m, teksts)
                if lid:
                    out.append((lid, None, m.group(0)))
        for m in RE_LIKUMS.finditer(teksts or ""):
            lid = self.likums(m.group(1), m.group(2), datums)
            if lid:
                pm = RE_PANTS.match(teksts[m.end():m.end() + 60])
                enk = None
                if pm:
                    sup = (pm.group(2) or "").translate(str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹", "0123456789"))
                    enk = "p" + pm.group(1) + (f"_{sup}" if sup else "")
                out.append((lid, enk, m.group(0).strip()))
        for m in RE_SALIKTS.finditer(teksts or ""):
            lid = self._izvele(self.vardi.get("#" + m.group(1).lower(), []), datums)
            if lid:
                pm = RE_PANTS.match(teksts[m.end():m.end() + 60])
                out.append((lid, "p" + pm.group(1) if pm else None, m.group(0)))
        for m in RE_MK.finditer(teksts or ""):
            d = f"{m.group(2)}-{MENESI[m.group(4).lower()]:02d}-{int(m.group(3)):02d}"
            veids = next((v for k, v in MK_VEIDI.items() if m.group(5).lower().startswith(k)), None)
            for lid in self.mk.get((veids, d, m.group(6)), [])[:1]:
                out.append((lid, None, m.group(0)))
        return out


if __name__ == "__main__":
    import sqlite3
    import sys
    from pathlib import Path
    import os
    c = sqlite3.connect(os.environ.get("LIKUMI_DB") or Path(__file__).resolve().parent.parent / "dati" / "likumi.db")
    r = Atrisinatajs(c)
    for t in sys.argv[1:] or ["Izdoti saskaņā ar Ministru kabineta iekārtas likuma 15.panta otro daļu",
                              'Grozījumi likumā "Par valsts un pašvaldību mantas atsavināšanu"',
                              "Grozījumi Ministru kabineta 2005. gada 20. septembra noteikumos Nr. 716",
                              "Izdoti saskaņā ar Latvijas Republikas Izglītības likuma 58.panta 2.punktu"]:
        print(t, "->", r.atrast(t, "2006-01-01"))
