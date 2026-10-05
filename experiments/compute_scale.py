#!/usr/bin/env python3
import json,math
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
counts=json.loads((ROOT/"experiments/gemi-counts.json").read_text())
rows=[]
for name,n in [("Top 1.000 (seed)",1000),("Ενεργές ΑΕ",counts["legal_forms"]["AE"]),("ΑΕ/ΕΠΕ/ΙΚΕ — proxy καταθετών",counts["capital_companies_proxy"]),("Όλες οι ενεργές εγγραφές",counts["active"]),("Όλες οι καταστάσεις στο μοντέλο",counts["all_statuses_same_model"])]:
 discovery=math.ceil(n/200)
 rows.append(dict(scenario=name,companies=n,discovery_calls=discovery,
                  days_min_2=(2*n+discovery)/8500,days_one_pdf_3=(3*n+discovery)/8500,
                  days_three_pdfs_5=(5*n+discovery)/8500,days_3_at_11520=(3*n+discovery)/11520,
                  days_3_with_20pct_reserved=(3*n+discovery)/6800))
(ROOT/"experiments/results/fill-days.json").write_text(json.dumps(rows,ensure_ascii=False,indent=2))
print("| Σενάριο | N | 2 κλήσεις, 8.500/ημ. | 3 κλήσεις, 8.500/ημ. | 5 κλήσεις, 8.500/ημ. | 3 κλήσεις, 11.520/ημ. |")
print("|---|---:|---:|---:|---:|---:|")
for r in rows:
 print(f'| {r["scenario"]} | {r["companies"]:,} | {r["days_min_2"]:.2f} | {r["days_one_pdf_3"]:.2f} | {r["days_three_pdfs_5"]:.2f} | {r["days_3_at_11520"]:.2f} |')

