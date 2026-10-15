#!/usr/bin/env python3
"""marker on the held-out sets, same truth and denominators as heldout_esef.py
and elp_crossyear.py. Parser rules are frozen; this script only runs and scores.

marker runs on the text layer (disable_ocr): CPU OCR with the surya VLM costs
minutes per page. Its JSON is cached beside each PDF (<stem>.marker.json).
  marker      marker tables -> existing core parser (company scope, current year)
  marker-geo  marker tables -> geo_extract (group/company scope, year_offset)
Run with experiments/.venv-marker/bin/python.
"""
import json, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "experiments"))
import parsing_benchmark as pb  # noqa: E402
import geo_extract  # noqa: E402
import heldout_esef as he  # noqa: E402
import elp_crossyear as elp  # noqa: E402
import esef_probe  # noqa: E402

ENGINES = ("marker", "marker-geo")


def marker_data(pdf):
    cache = pdf.with_suffix(".marker.json")
    if not cache.exists():
        pb.marker_json(pdf, False, False, target=cache)
    return json.loads(cache.read_text())


def read(pdf, engine, **geo_kw):
    data = marker_data(pdf)
    if engine == "marker":
        return pb.marker_extract(pdf, data)
    original = geo_extract.extract_pages
    try:
        geo_extract.extract_pages = lambda p, t=None: original(p, t, **geo_kw)
        return pb.marker_extract(pdf, data, use_geo=True)
    finally:
        geo_extract.extract_pages = original


def esef():
    filings = he.all_filings()
    rows = []
    for fragment, year, url in he.CASES:
        match = [f for f in filings if fragment in f["name"].upper() and f["period_end"].startswith(str(year))]
        if len(match) != 1:
            print(fragment, year, "ESEF filing not unique:", len(match)); continue
        truth = esef_probe.summarize(match[0])
        pdf = he.CACHE / f"{fragment.split()[0].lower()}_{year}.pdf"
        if not pdf.exists():
            rows.append(dict(company=fragment, year=year, engine="marker*", truth=truth, result=None,
                             error="PDF not cached; not measured (no download in this script)"))
            print(fragment, year, "PDF not cached; not measured"); continue
        for engine in ENGINES:
            for scope in ("group", "company"):
                key = {"group": "consolidated", "company": "separate"}[scope]
                facts = {k: v[key] for k, v in truth.items() if key in v}
                if not facts or (engine == "marker" and scope == "group"):
                    continue
                started = time.perf_counter()
                try:
                    got = read(pdf, engine) if engine == "marker" else read(pdf, engine, target_scope=scope)
                    error = None
                except Exception as e:
                    got, error = {"figures": {}}, f"{type(e).__name__}: {str(e)[:200]}"
                res = he.score(facts, got)
                rows.append(dict(company=fragment, year=year, engine=engine, scope=scope, truth=facts, result=res,
                                 fiscal_year=got.get("fiscal_year"), status=got.get("status"),
                                 reason=got.get("reason"), error=error,
                                 seconds=round(time.perf_counter() - started, 1), notes=(got.get("notes") or [])[:30]))
                c = sum(v == "correct" for v in res.values()); wr = [k for k, v in res.items() if v.startswith("WRONG")]
                print(f"{fragment[:18]:18} {year} {engine:10} {scope:7} {c}/{len(res)} wrong={wr} "
                      f"fy={got.get('fiscal_year')} {got.get('reason') or ''} {error or ''}", flush=True)
    (pb.OUT / "heldout-esef-marker.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2))


def crossyear():
    readings = {}
    for pdf in sorted(elp.CACHE.glob("*_20[0-9][0-9].pdf")):
        company, year = pdf.stem.rsplit("_", 1)
        for engine in ENGINES:
            for offset in (0, 1):
                if engine == "marker" and offset:
                    continue
                started = time.perf_counter()
                try:
                    got = read(pdf, engine) if engine == "marker" else read(pdf, engine, year_offset=offset)
                    error = None
                except Exception as e:
                    got, error = {"figures": {}}, f"{type(e).__name__}: {str(e)[:200]}"
                readings[(company, engine, offset, int(year))] = dict(
                    fiscal_year=got.get("fiscal_year"), status=got.get("status"), reason=got.get("reason"),
                    error=error, unit=got.get("unit_multiplier"), seconds=round(time.perf_counter() - started, 1),
                    values={k: v["value"] for k, v in got.get("figures", {}).items() if k in elp.FIELDS})
                r = readings[(company, engine, offset, int(year))]
                print(f"{company:12} {year} {engine:10} {'prior' if offset else 'current':7} fy={r['fiscal_year']} "
                      f"{r['status']} {r['reason'] or ''} n={len(r['values'])} {error or ''}", flush=True)
    rows = []
    # same_engine: the elp_crossyear.py rule (the core parser has no comparative read, so it never pairs).
    # hybrid: marker core current value against marker-geo's comparative read. Reported separately.
    for pairing, partner in (("same_engine", None), ("hybrid", "marker-geo")):
        for (company, engine, offset, year), cur in readings.items():
            if offset or (pairing == "hybrid" and engine != "marker"):
                continue
            nxt = readings.get((company, partner or engine, 1, year + 1))
            for field in elp.FIELDS:
                a = cur["values"].get(field)
                b = nxt["values"].get(field) if nxt else None
                if nxt is None:
                    verdict = "no_next_year_doc"
                elif a is None and b is None:
                    verdict = "both_missing"
                elif a is None or b is None:
                    verdict = "one_missing"
                else:
                    verdict = "agree" if elp.close(a, b) else "DISAGREE"
                rows.append(dict(pairing=pairing, company=company, year=year, engine=engine, field=field,
                                 current=a, comparative_next=b, verdict=verdict))
    (pb.OUT / "elp-crossyear-marker.json").write_text(json.dumps(dict(
        readings={"|".join(map(str, k)): v for k, v in readings.items()}, pairs=rows), ensure_ascii=False, indent=2))
    print()
    for pairing, engine in (("same_engine", "marker"), ("same_engine", "marker-geo"), ("hybrid", "marker")):
        sel = [r for r in rows if r["engine"] == engine and r["pairing"] == pairing]
        paired = [r for r in sel if r["verdict"] != "no_next_year_doc"]
        count = lambda v: sum(r["verdict"] == v for r in paired)
        emitted = [r for r in sel if r["current"] is not None]
        in_pair = [r for r in paired if r["current"] is not None]
        print(f"{engine:10} {pairing:11} values emitted {len(emitted)} | in paired years {len(in_pair)} | "
              f"paired fields {len(paired)}: agree {count('agree')} DISAGREE {count('DISAGREE')} "
              f"one_missing {count('one_missing')} both_missing {count('both_missing')}")

if __name__ == "__main__":
    {"esef": esef, "elp": crossyear}[sys.argv[1]]()
