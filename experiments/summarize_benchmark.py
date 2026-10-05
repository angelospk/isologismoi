#!/usr/bin/env python3
"""Re-score saved predictions. No downloads; no publication."""
import json,statistics
from pathlib import Path
from parsing_benchmark import ROOT,OUT,score
supp=json.loads((ROOT/"experiments/fallback-golden.json").read_text())
groups={}
perfield={}
for path in sorted(OUT.glob("*--*.json")):
 d=json.loads(path.read_text()); name=d["backend"]
 group=groups.setdefault(name,dict(backend=name,pdfs=0,real_pdfs=0,errors=0,empty_outputs=0,
                                  original_expected=0,original_correct=0,original_anchored=0,
                                  original_wrong=0,confident_wrong=0,fallback_expected=0,
                                  fallback_correct=0,fallback_anchored=0,fallback_wrong=0,
                                  fallback_confident_wrong=0,forbidden_emissions=0,
                                  metadata_matches=0,status_matches=0,seconds=[]))
 fixture=ROOT/"extractor/fixtures"/d["pdf"]
 gp=fixture.with_suffix(".golden.json")
 gold=json.loads(gp.read_text()) if gp.exists() else dict(status="unparseable",reason="no_text_layer",figures={},ar_gemi=None,fiscal_year=None,currency="EUR",unit_multiplier=1)
 group["pdfs"]+=1;group["real_pdfs"]+=not d["pdf"].startswith("_synthetic")
 group["seconds"].append(d["seconds"])
 group["original_expected"]+=len(gold["figures"])
 fallback=supp.get(fixture.stem)
 if fallback:group["fallback_expected"]+=len(fallback["figures"])
 if d["error"]:
  group["errors"]+=1
 else:
  m=score(gold,d["prediction"]);d["metrics"]=m
  group["empty_outputs"]+=m["refusal"]
  group["original_correct"]+=m["correct_fields"]
  group["original_anchored"]+=m["anchored_correct_fields"]
  group["original_wrong"]+=len(m["wrong_fields"])
  group["metadata_matches"]+=m["metadata_match"]
  group["status_matches"]+=m["status_match"]
  high=lambda k:not name.startswith("gemma3") or float(d["prediction"]["figures"][k].get("confidence",0))>=0.9
  group["confident_wrong"]+=sum(high(k) for k in m["wrong_fields"])
  for k,exp in gold["figures"].items():
   field=perfield.setdefault(name,{}).setdefault(k,dict(expected=0,correct=0,wrong=0,missing=0))
   field["expected"]+=1
   field["wrong"]+=k in m["wrong_fields"]
   field["missing"]+=k in m["missing_fields"]
   field["correct"]+=k not in m["wrong_fields"] and k not in m["missing_fields"] and m["context_match"]
  if fallback:
   fm=score(dict(status="needs_review",**fallback),d["prediction"]);d["fallback_metrics"]=fm
   fm["forbidden_emissions"]=[k for k in fallback["must_omit"] if k in d["prediction"]["figures"]]
   group["fallback_correct"]+=fm["correct_fields"]
   group["fallback_anchored"]+=fm["anchored_correct_fields"]
   group["fallback_wrong"]+=len(fm["wrong_fields"])
   group["fallback_confident_wrong"]+=sum(high(k) for k in fm["wrong_fields"])
   group["forbidden_emissions"]+=len(fm["forbidden_emissions"])
 path.write_text(json.dumps(d,ensure_ascii=False,indent=2,default=str))
for g in groups.values():
 times=g.pop("seconds");g["seconds_mean"]=statistics.mean(times);g["seconds_median"]=statistics.median(times)
 g["api_cost_eur_per_pdf"]=0
(OUT/"summary.json").write_text(json.dumps(dict(backends=list(groups.values()),per_field=perfield),ensure_ascii=False,indent=2))
print("| Μέθοδος | PDF | Αγκυρωμένα σωστά / original golden | Άδεια έξοδος | Σφάλματα | Λάθος υποψήφια ποσά | Μέσος χρόνος s/PDF |")
print("|---|---:|---:|---:|---:|---:|---:|")
for g in groups.values():
 value=f'{g["original_anchored"]}/{g["original_expected"]}' if g["original_expected"] else "N/A"
 print(f'| {g["backend"]} | {g["pdfs"]} | {value} | {g["empty_outputs"]}/{g["pdfs"]} | {g["errors"]} | {g["original_wrong"]} | {g["seconds_mean"]:.2f} |')

