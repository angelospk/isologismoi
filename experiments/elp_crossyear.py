#!/usr/bin/env python3
"""ELP evaluation without a hand-made answer key: cross-year agreement.

The year-Y figure is printed twice, in two independent documents: as the
current column of the Y filing and as the comparative column of the Y+1
filing. A parser that reads both and gets the same number has very likely
read it right; a disagreement means at least one reading is wrong (or the
filer restated). Parser rules are frozen; this script only runs and scores.
PDFs are public company-website copies, cached locally and not committed.
"""
import json, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "experiments"))
import parsing_benchmark as pb  # noqa: E402
import geo_extract  # noqa: E402

CACHE = ROOT / "experiments/elp-cache"
OUT = ROOT / "experiments/results/elp-crossyear.json"
FIELDS = ("turnover", "pre_tax_profit", "net_profit", "total_assets", "equity")


def read(pdf, engine, year_offset=0):
    if engine == "pdfplumber":
        return pb.semantic.extract(pdf.read_bytes()) if year_offset == 0 else None
    original = geo_extract.extract_pages
    try:
        geo_extract.extract_pages = lambda p, t=None: original(p, t, year_offset=year_offset)
        return pb.geo(pdf, ocr=engine == "geo-ocr")
    finally:
        geo_extract.extract_pages = original


def close(a, b):
    return abs(a - b) <= max(1.0, abs(b) * 0.0005)


def main():
    docs = sorted(CACHE.glob("*_20[0-9][0-9].pdf"))
    readings = {}
    for pdf in docs:
        company, year = pdf.stem.rsplit("_", 1)
        for engine in ("pdfplumber", "geo", "geo-ocr"):
            for offset in (0, 1):
                started = time.perf_counter()
                try:
                    got, error = read(pdf, engine, offset), None
                except Exception as e:
                    got, error = {"figures": {}}, f"{type(e).__name__}: {str(e)[:200]}"
                if got is None:
                    continue
                fy = got.get("fiscal_year")
                readings[(company, engine, offset, int(year))] = dict(
                    fiscal_year=fy, status=got.get("status"), reason=got.get("reason"), error=error,
                    unit=got.get("unit_multiplier"), seconds=round(time.perf_counter() - started, 1),
                    values={k: v["value"] for k, v in got.get("figures", {}).items() if k in FIELDS})
                r = readings[(company, engine, offset, int(year))]
                print(f"{company:12} {year} {engine:10} {'prior' if offset else 'current':7} fy={fy} "
                      f"{r['status']} {r['reason'] or ''} n={len(r['values'])} {error or ''}", flush=True)
    rows = []
    for (company, engine, offset, year), cur in readings.items():
        if offset:
            continue
        nxt = readings.get((company, engine, 1, year + 1))
        for field in FIELDS:
            a = cur["values"].get(field)
            b = nxt["values"].get(field) if nxt else None
            if nxt is None:
                verdict = "no_next_year_doc"
            elif a is None and b is None:
                verdict = "both_missing"
            elif a is None or b is None:
                verdict = "one_missing"
            else:
                verdict = "agree" if close(a, b) else "DISAGREE"
            rows.append(dict(company=company, year=year, engine=engine, field=field,
                             current=a, comparative_next=b, verdict=verdict))
    OUT.write_text(json.dumps(dict(readings={"|".join(map(str, k)): v for k, v in readings.items()},
                                   pairs=rows), ensure_ascii=False, indent=2))
    print()
    for engine in ("pdfplumber", "geo", "geo-ocr"):
        sel = [r for r in rows if r["engine"] == engine]
        paired = [r for r in sel if r["verdict"] != "no_next_year_doc"]
        count = lambda v: sum(r["verdict"] == v for r in paired)
        single = [r for r in sel if r["verdict"] == "no_next_year_doc" and r["current"] is not None]
        print(f"{engine:10} paired fields {len(paired)}: agree {count('agree')} DISAGREE {count('DISAGREE')} "
              f"one_missing {count('one_missing')} both_missing {count('both_missing')} | "
              f"unpaired values emitted {len(single)}")


if __name__ == "__main__":
    main()
