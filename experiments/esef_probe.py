#!/usr/bin/env python3
"""Probe Greek ESEF filings on filings.xbrl.org as automatic ground truth. Read-only, public API."""
import json, sys, urllib.parse, urllib.request
from pathlib import Path

BASE = "https://filings.xbrl.org"
OUT = Path(__file__).resolve().parents[1] / "experiments/esef-cache"
CONCEPTS = {
    "turnover": ["ifrs-full:Revenue"],
    "net_profit": ["ifrs-full:ProfitLoss"],
    "pre_tax_profit": ["ifrs-full:ProfitLossBeforeTax"],
    "total_assets": ["ifrs-full:Assets"],
    "equity": ["ifrs-full:Equity"],
}


def get(url, binary=False):
    req = urllib.request.Request(url, headers={"User-Agent": "isologismoi-research/0.1"})
    with urllib.request.urlopen(req, timeout=60) as r:
        data = r.read()
    return data if binary else json.loads(data)


def filings(limit):
    flt = urllib.parse.quote(json.dumps([{"name": "country", "op": "eq", "val": "GR"}]))
    url = f"{BASE}/api/filings?filter={flt}&page[size]={limit}&sort=-date_added&include=entity"
    d = get(url)
    names = {e["id"]: e["attributes"].get("name") for e in d.get("included", []) if e["type"] == "entity"}
    for f in d["data"]:
        a = f["attributes"]
        ent = f["relationships"]["entity"]["data"]["id"]
        yield dict(id=a["fxo_id"], period_end=a["period_end"], json=a.get("json_url"),
                   report=a.get("report_url"), package=a.get("package_url"),
                   errors=a.get("error_count"), name=names.get(ent))


def facts(filing):
    OUT.mkdir(exist_ok=True)
    cache = OUT / (filing["id"] + ".json")
    if not cache.exists():
        cache.write_bytes(get(BASE + filing["json"], binary=True))
    return json.loads(cache.read_text())


def summarize(filing):
    data = facts(filing)
    year = int(filing["period_end"][:4])
    out = {}
    for key, concepts in CONCEPTS.items():
        for fid, f in data["facts"].items():
            d = f["dimensions"]
            if d.get("concept") not in concepts or d.get("unit") != "iso4217:EUR":
                continue
            period = d.get("period", "")
            if not period.endswith(f"{year}-12-31T00:00:00") and not period.endswith(f"{year + 1}-01-01T00:00:00"):
                continue
            axes = {k: v for k, v in d.items() if ":" in k and k not in ("concept",)}
            scope = "consolidated"
            if axes.get("ifrs-full:ConsolidatedAndSeparateFinancialStatementsAxis", "").endswith("SeparateMember"):
                scope = "separate"
            elif axes:
                continue  # any other dimension is a breakdown, not the statement total
            out.setdefault(key, {})[scope] = float(f["value"])
    return out


def main():
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 20
    rows = []
    for f in filings(limit):
        if not f["period_end"].startswith("2024"): continue
        try:
            s = summarize(f)
        except Exception as e:
            s = {"error": f"{type(e).__name__}: {e}"[:200]}
        rows.append(dict(f, figures=s))
        sep = sum("separate" in v for v in s.values() if isinstance(v, dict))
        print(f'{(f["name"] or "")[:30]:30} {f["period_end"]} errs={f["errors"]} keys={len(s)} separate={sep} '
              f'report={f["report"].rsplit("/", 1)[-1] if f["report"] else None}', flush=True)
    (OUT / "_index.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
