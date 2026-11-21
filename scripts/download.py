#!/usr/bin/env python3
"""Ielādē vai atjaunina publisko datubāzi data/pb-likumi.db pēc manifesta latest.json.

  python3 scripts/download.py                 # adrese un atslēga no faila .env prasmes saknē
  python3 scripts/download.py --parbaudit     # tikai salīdzina lokālo versiju ar publicēto
  python3 scripts/download.py --latest URL --atslega age.key

Fails .env (prasmes saknē, nav repozitorijā). Pirmajā palaišanas reizē to izveido no sagataves .env.example;
tajā jāieraksta atslēga, ko dod datu uzturētājs:
  LATEST_URL=https://dati.<domēns>/pb-likumi/latest.json
  AGE_KEY=AGE-SECRET-KEY-1...          # pati atslēga vai ceļš uz failu ar to
Secība: komandrinda, tad vides mainīgie <PROJEKTS>_LATEST_URL un <PROJEKTS>_AGE_KEY, tad .env.

latest.json -> gabali (atsākami) -> katra gabala sha256 -> age -d -> zstd -d -> visas DB sha256 -> pārdēvē par
data/pb-likumi.db. Ja versija nav mainījusies, neko nedara. Atsakās no datubāzes ar schema_version, ko rīks
nesaprot (tad vispirms jāatjauno prasme).

Vajag komandas `age` un `zstd`. Tikai Python standarta bibliotēka. Manifesta adrese: https://..., file://... vai ceļš.
"""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

SAKNE = Path(__file__).resolve().parent.parent
PROJEKTS = "pb-likumi"
ATBALSTITA_SHEMA = 1    # augstākā publiskās DB schema_version, ko rīki saprot; jāsakrīt ar search.py

V = PROJEKTS.upper().replace("-", "_")                    # vides mainīgo prefikss

DATI = SAKNE / "data"
DB = DATI / f"{PROJEKTS}.db"
VERSIJA = DATI / "versija.json"
ENV = SAKNE / ".env"


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, file=sys.stderr, flush=True)


def iestatijums(nosaukums: str) -> str:
    """Vides mainīgais <PROJEKTS>_<nosaukums>; ja tāda nav, rinda <nosaukums>=... failā .env prasmes saknē."""
    if os.environ.get(f"{V}_{nosaukums}"):
        return os.environ[f"{V}_{nosaukums}"]
    if not ENV.exists() and ENV.with_name(".env.example").exists():       # sagatave -> .env (nav repozitorijā)
        shutil.copyfile(ENV.with_name(".env.example"), ENV)
        log(f"izveidots {ENV} no sagataves .env.example")
    if ENV.exists():
        for rinda in ENV.read_text(encoding="utf-8-sig").splitlines():
            k, _, v = rinda.partition("=")
            if k.strip() == nosaukums and not rinda.lstrip().startswith("#"):
                return v.strip().strip("'\"")
    return ""


def adrese(x: str) -> str:
    """Lokāls ceļš -> file:// adrese; http(s) un file paliek."""
    return x if urllib.parse.urlparse(x).scheme in ("http", "https", "file") else Path(x).resolve().as_uri()


def lasit(url: str, no: int = 0):
    rq = urllib.request.Request(url, headers={"User-Agent": f"{PROJEKTS}-skill/1.0"})
    if no:
        rq.add_header("Range", f"bytes={no}-")
    return urllib.request.urlopen(rq, timeout=120)


def sha256(cels: Path) -> str:
    h = hashlib.sha256()
    with open(cels, "rb") as f:
        while b := f.read(1 << 22):
            h.update(b)
    return h.hexdigest()


def gabals(p: dict, merkis: Path):
    """Lejupielādē vienu gabalu; ja daļa jau ir, turpina (Range). Pārbauda izmēru un sha256."""
    if merkis.exists() and merkis.stat().st_size == p["size"] and sha256(merkis) == p["sha256"]:
        return
    tmp = merkis.with_name(merkis.name + ".part")
    for meginajums in range(3):
        ir = tmp.stat().st_size if tmp.exists() else 0
        if ir > p["size"]:
            tmp.unlink()
            ir = 0
        url = adrese(p["url"])
        try:
            if ir < p["size"]:
                with lasit(url, ir if not url.startswith("file:") else 0) as r, open(tmp, "ab" if ir else "wb") as f:
                    if ir and (url.startswith("file:") or getattr(r, "status", 200) != 206):
                        if url.startswith("file:"):
                            r.read(ir)                     # file:// nav Range: izlaiž jau esošo daļu
                        else:
                            f.truncate(0)                  # serveris Range neievēro: no sākuma
                    shutil.copyfileobj(r, f, 1 << 22)
        except OSError as e:
            log(f"   {p['name']}: {e}; mēģina vēlreiz")
            time.sleep(3)
            continue
        if tmp.stat().st_size == p["size"] and sha256(tmp) == p["sha256"]:
            tmp.rename(merkis)
            return
        log(f"   {p['name']}: izmērs vai sha256 nesakrīt; lejupielādē no jauna")
        tmp.unlink(missing_ok=True)
    sys.exit(f"KĻŪDA: neizdevās lejupielādēt {p['name']}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--latest", default=iestatijums("LATEST_URL"), help="manifesta latest.json adrese vai ceļš")
    ap.add_argument("--atslega", default=iestatijums("AGE_KEY"),
                    help="age privātā atslēga (AGE-SECRET-KEY-1...) vai fails ar to")
    ap.add_argument("--parbaudit", action="store_true", help="neko nelejupielādē: tikai salīdzina versijas")
    ap.add_argument("--force", action="store_true", help="ielādēt arī tad, ja versija nav mainījusies")
    a = ap.parse_args()
    if not a.latest:
        sys.exit(f"KĻŪDA: nav manifesta adreses: ieraksti LATEST_URL=... failā {ENV}")
    with lasit(adrese(a.latest)) as r:
        m = json.loads(r.read().decode("utf-8"))
    if not m.get("version"):
        sys.exit("manifestā nav versijas: datubāze vēl nav publicēta")
    veca = json.loads(VERSIJA.read_text()) if VERSIJA.exists() and DB.exists() else {}
    print(json.dumps({"publiceta": m["version"], "lokala": veca.get("version"), "dati_uz": m.get("dati_uz"),
                      "schema_version": m.get("schema_version"), "izmers_MB": round(m.get("size", 0) / 1e6)},
                     ensure_ascii=False))
    if int(m.get("schema_version") or 0) > ATBALSTITA_SHEMA:
        sys.exit(f"KĻŪDA: publicētās DB shēmas versija {m['schema_version']} ir jaunāka par šīs prasmes atbalstīto "
                 f"({ATBALSTITA_SHEMA}): vispirms atjauno prasmi (git pull)")
    if a.parbaudit or (veca.get("version") == m["version"] and not a.force):
        log("datubāze ir aktuāla" if veca.get("version") == m["version"] else "ir jaunāka versija")
        return
    for rks in ("age", "zstd"):
        if not shutil.which(rks):
            sys.exit(f"KĻŪDA: nav komandas `{rks}` (Linux: apt install {rks}; macOS: brew install {rks}; "
                     f"Windows: winget install FiloSottile.age Meta.Zstandard)")
    tiesa = a.atslega.startswith("AGE-SECRET-KEY-")           # pati atslēga, nevis ceļš
    if not a.atslega or not (tiesa or Path(a.atslega).exists()):
        sys.exit(f"KĻŪDA: nav atslēgas. Atver failu {ENV} un rindā AGE_KEY= ieraksti no datu uzturētāja "
                 "saņemto atslēgu (AGE-SECRET-KEY-1...), tad palaid vēlreiz.")

    mape = DATI / "lejupielade" / m["version"]
    mape.mkdir(parents=True, exist_ok=True)
    for i, p in enumerate(m["parts"], 1):
        log(f"gabals {i}/{len(m['parts'])}: {p['name']} ({p['size'] / 1e6:.0f} MB)")
        gabals(p, mape / p["name"])
    tmp = DB.with_name(DB.name + ".tmp")
    atslegas_fails = Path(a.atslega)
    if tiesa:                                                 # age atslēgu lasa tikai no faila
        atslegas_fails = DATI / "lejupielade" / "age.key"
        atslegas_fails.touch(mode=0o600)
        atslegas_fails.write_text(a.atslega + "\n")
    log("atšifrē (age) un atspiež (zstd)")
    with open(tmp, "wb") as izv:
        age = subprocess.Popen(["age", "-d", "-i", str(atslegas_fails)], stdin=subprocess.PIPE, stdout=subprocess.PIPE)
        zst = subprocess.Popen(["zstd", "-d", "-q", "-c"], stdin=age.stdout, stdout=izv)
        age.stdout.close()
        try:
            for p in m["parts"]:
                with open(mape / p["name"], "rb") as f:
                    shutil.copyfileobj(f, age.stdin, 1 << 22)
            age.stdin.close()
        except BrokenPipeError:
            pass
        kluda = age.wait() or zst.wait()
        if tiesa:
            atslegas_fails.unlink(missing_ok=True)
        if kluda:
            tmp.unlink(missing_ok=True)
            sys.exit("KĻŪDA: atšifrēšana vai atspiešana neizdevās (nepareiza atslēga?)")
    if sha256(tmp) != m["sha256"]:
        tmp.unlink()
        sys.exit("KĻŪDA: datubāzes sha256 nesakrīt ar manifestu")
    tmp.replace(DB)                                           # aizstāj veco, pārdēvējot
    VERSIJA.write_text(json.dumps({k: v for k, v in m.items() if k != "parts"}, ensure_ascii=False, indent=1) + "\n")
    shutil.rmtree(DATI / "lejupielade", ignore_errors=True)
    log(f"gatavs: {DB} ({DB.stat().st_size / 1e6:.0f} MB), versija {m['version']}, dati uz {m.get('dati_uz')}")


if __name__ == "__main__":
    main()
