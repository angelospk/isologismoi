#!/usr/bin/env python3
"""Held-out evaluation with machine-readable ground truth. Read-only public sources.

Document: the Greek annual financial report PDF a listed company publishes.
Truth: the ESEF iXBRL facts of the same company and year from filings.xbrl.org.
The tagged numbers are language-independent, so the English ESEF version is a
valid answer key for the Greek PDF. Nobody reads the answer by eye.

ESEF mandates tags on the consolidated statements, so the comparison is on
the group column. Separate (company) facts are compared when the filer tagged
them with ConsolidatedAndSeparateFinancialStatementsAxis=SeparateMember.
Parser rules are frozen: this script only runs and scores.
"""
import json, sys, time, urllib.parse, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "experiments"))
import parsing_benchmark as pb  # noqa: E402
import esef_probe  # noqa: E402
import geo_extract  # noqa: E402

CACHE = ROOT / "experiments/heldout-cache"
OUT = ROOT / "experiments/results/heldout-esef.json"
UA = {"User-Agent": "isologismoi-research/0.1 (offline benchmark)"}

# name fragment in filings.xbrl.org, fiscal year, Greek PDF URL. Chosen before
# any parser run, by availability of a direct public PDF link only.
CASES = [
    ("ΤΕΧΝΙΚΗ ΟΛΥΜΠΙΑΚΗ", 2021, "https://athens.euronext.com/el/documents/10180/43442/%CE%9F%CE%B9%CE%BA%CE%BF%CE%BD%CE%BF%CE%BC%CE%B9%CE%BA%CE%AE%20%CE%88%CE%BA%CE%B8%CE%B5%CF%83%CE%B7%20%CE%A4%CE%95%CE%A7%CE%9D%CE%99%CE%9A%CE%97%20%CE%9F%CE%9B%CE%A5%CE%9C%CE%A0%CE%99%CE%91%CE%9A%CE%97%20%CE%91.%CE%95.%20%282021%2C%CE%95%CF%84%CE%AE%CF%83%CE%B9%CE%BF%CF%82%20%CE%99%CF%83%CE%BF%CE%BB%CE%BF%CE%B3%CE%B9%CF%83%CE%BC%CF%8C%CF%82%2C%CE%9C%CE%B7%CF%84%CF%81%CE%B9%CE%BA%CE%AE-%CE%95%CE%BD%CE%BF%CF%80%CE%BF%CE%B9%CE%B7%CE%BC%CE%AD%CE%BD%CE%B7%29.pdf/8d9dae58-8dde-4a6d-9de8-50b04c457d62"),
    ("QUEST", 2024, "https://www.quest.gr/sites/default/files/2025-04/Quest%20Holdings%20Fin%20Stmts%2031%2012%202024%20GR_GT%209%204%202025_0.pdf"),
    ("AUTOHELLAS", 2024, "https://www.autohellas.gr/wp-content/uploads/2025/06/ANNUAL-REPORT-2024-GR.pdf"),
]


def all_filings():
    path = CACHE / "_gr_filings.json"
    if path.exists():
        return json.loads(path.read_text())
    flt = urllib.parse.quote(json.dumps([{"name": "country", "op": "eq", "val": "GR"}]))
    rows, page = [], 1
    while True:
        url = f"{esef_probe.BASE}/api/filings?filter={flt}&page[size]=100&page[number]={page}&include=entity"
        d = esef_probe.get(url)
        names = {e["id"]: e["attributes"].get("name") for e in d.get("included", []) if e["type"] == "entity"}
        for f in d["data"]:
            a = f["attributes"]
            rows.append(dict(id=a["fxo_id"], period_end=a["period_end"], json=a.get("json_url"),
                             name=names.get(f["relationships"]["entity"]["data"]["id"]) or ""))
        if len(d["data"]) < 100:
            break
        page += 1
    CACHE.mkdir(exist_ok=True)
    path.write_text(json.dumps(rows, ensure_ascii=False))
    return rows


def fetch_pdf(url, name):
    path = CACHE / f"{name}.pdf"
    if not path.exists():
        req = urllib.request.Request(url, headers=UA)
        with urllib.request.urlopen(req, timeout=180) as r:
            data = r.read()
        if not data.startswith(b"%PDF"):
            raise ValueError("not a PDF")
        path.write_bytes(data)
        time.sleep(2)
    return path


def score(truth, got):
    out = {}
    for key, value in truth.items():
        fig = got.get("figures", {}).get(key)
        if fig is None:
            out[key] = "missing"
        else:
            out[key] = "correct" if abs(fig["value"] - value) <= max(1.0, abs(value) * 0.0005) else \
                f"WRONG {fig['value']} vs {value}"
    return out


def main():
    filings = all_filings()
    CACHE.mkdir(exist_ok=True)
    rows = []
    for fragment, year, url in CASES:
        match = [f for f in filings if fragment in f["name"].upper() and f["period_end"].startswith(str(year))]
        if len(match) != 1:
            print(fragment, year, "ESEF filing not unique:", len(match)); continue
        truth = esef_probe.summarize(match[0])
        name = f"{fragment.split()[0].lower()}_{year}"
        pdf = fetch_pdf(url, name)
        for engine in ("geo", "geo-ocr", "pdfplumber"):
            started = time.perf_counter()
            for scope in ("group", "company"):
                facts = {k: v[{"group": "consolidated", "company": "separate"}[scope]]
                         for k, v in truth.items() if {"group": "consolidated", "company": "separate"}[scope] in v}
                if not facts or (engine == "pdfplumber" and scope == "group"):
                    continue
                try:
                    if engine == "pdfplumber":
                        got = pb.semantic.extract(pdf.read_bytes())
                    else:
                        got = geo_on(pdf, engine == "geo-ocr", scope)
                    error = None
                except Exception as e:
                    got, error = {"figures": {}}, f"{type(e).__name__}: {str(e)[:200]}"
                res = score(facts, got)
                rows.append(dict(company=fragment, year=year, engine=engine, scope=scope, truth=facts,
                                 result=res, fiscal_year=got.get("fiscal_year"), status=got.get("status"),
                                 reason=got.get("reason"), error=error, seconds=round(time.perf_counter() - started, 1),
                                 notes=(got.get("notes") or [])[:30]))
                c = sum(v == "correct" for v in res.values()); wr = [k for k, v in res.items() if v.startswith("WRONG")]
                print(f"{fragment[:18]:18} {year} {engine:10} {scope:7} {c}/{len(res)} wrong={wr} "
                      f"fy={got.get('fiscal_year')} {got.get('reason') or ''} {error or ''}", flush=True)
    OUT.write_text(json.dumps(rows, ensure_ascii=False, indent=2))


def geo_on(pdf, ocr, scope):
    original = geo_extract.extract_pages
    try:
        geo_extract.extract_pages = lambda p, t=None: original(p, t, target_scope=scope)
        return pb.geo(pdf, ocr=ocr)
    finally:
        geo_extract.extract_pages = original


if __name__ == "__main__":
    main()
