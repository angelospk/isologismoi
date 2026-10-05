# Handoff — ΓΕΜΗ scale / parsing — 2026-10-04

## Εντολή συνέχισης
Ο Harold ζήτησε νέο top-level thread σε Opus λόγω quotas. Συνέχισε από τα υπάρχοντα αρχεία· μην επαναλάβεις την έρευνα. Όλα τα commands/αρχεία μέσω ssh minipc στο ~/isologismoi. Εξαίρεση: Grok CLI στο Mac, μόνο αν χρειαστεί νέα έρευνα. Ελληνικά, σύντομα, έως 5 στοιχεία ανά λίστα.

## Όρια
Φάση έρευνα + σχέδιο + μικρά πειράματα. Καμία αλλαγή production Cloudflare Worker/D1/secrets και κανένα push. Μην ψάξεις ή ανακτήσεις GEMI_API_KEY· η μεταγενέστερη αναφορά ότι υπάρχει τοπικά/Cloudflare δεν αναιρεί αυτό το όριο. Multimodal μόνο τοπικό, χωρίς χρέωση. Μακριές εργασίες σε tmux/nohup στο mini PC. Headroom παραμένει ενεργό, μην μειώσεις context window. Για νέο CLI/agent ακολούθησε headroom init --global ή headroom wrap. Διάβασε τα ισχύοντα AGENTS.md. Αν χρειαστεί Oracle, πρώτα ~/.config/agent-policy/oracle-vps.md. Μην κάνεις νέα delegation χωρίς ρητή εντολή. Εξωτερικά APIs βιβλιοθηκών: επιβεβαίωση με deepwiki-research όταν αβέβαια.

## Κατάσταση
Branch exp/parsing-benchmark, χωρίς commit/push κατά την προηγούμενη σύνοψη. Έλεγξε git status πριν γράψεις. worker/, extractor/, data/ δεν άλλαξαν.
Draft docs/research/2026-10-04-gemi-scale-and-parsing.md: placeholders __FILL_TABLE__, __BENCHMARK_SECTION__, __VERIFICATION__.
experiments/: parsing_benchmark.py, summarize_benchmark.py, test_benchmark.py, fallback-golden.json, gemi-counts.json, compute_scale.py, README.md.
results/: summary.json, fill-days.json και backend raw results.
Publicity: publicity-network-notes.md, publicity-evidence/, publicity_headless.py.
Αγνοημένα logs/πηγές/venvs/wheels στο experiments/research-sources/ και συναφείς φακέλους. Μην τα κάνεις commit.

## Ευρήματα προς επαλήθευση από αποθηκευμένα τεκμήρια
Πηγή statistics.businessportal.gr/demography/active, δημόσια Power BI queries. Snapshot 2026-10-04 18:06:39 UTC, δεύτερος έλεγχος ίδια σύνολα.
Ενεργές 1.023.685, όλες οι καταστάσεις 1.648.180.
ΑΕ 53.453, ΕΠΕ 18.105, ΙΚΕ 110.152, ΟΕ 92.525, ΕΕ 87.577, ατομικές 645.777.
181.710 ΑΕ/ΕΠΕ/ΙΚΕ = proxy στόχευσης, ΟΧΙ μετρημένοι ετήσιοι καταθέτες.
Swagger έως 200 εταιρείες/κλήση και totalCount, χωρίς modifiedSince.
Προφίλ+εκπρόσωποι 1 κλήση, έγγραφα 1, PDF 1 ανά αρχείο. Με 3/company και 8.500/day: 1.000 = 0,35 ημέρες, ενεργές ΑΕ = 18,90, proxy = 64,24.
CSV/ZIP data.gov.gr κενό CSV. Δεν βρέθηκε πλήρες dump εταιρειών/PDF.
Δημόσιοι όροι ODC-BY, δεν βρέθηκε ρητή απαγόρευση bulk. Ειδικοί όροι έγκρισης key παραμένουν ανοιχτοί.
Publicity για 194123801000 / STRIDE Ι.Κ.Ε.: browser POST /api/company/details 200, query/token/language και reCAPTCHA. Tokenless HTTP 400, κανονικό Chrome headless στο mini PC 429. Δεν τεκμηριώθηκε μόνιμο replay ή εξαίρεση rate limit. Μην παρακάμψεις CAPTCHA.
Δύο OpenCode delegated attempts απέτυχαν στον provider· την έρευνα έκανε ο κύριος agent.

## Benchmark
6 πραγματικά PDF + 1 synthetic blank. Μόνο 2 έχουν αρχικά αριθμητικά golden: 12 πεδία.
pdfplumber 12/12 σωστά, 5/7 άδειες έξοδοι, 0 errors, 2,88 s/PDF.
PyMuPDF 12/12, 5/7, 0, 0,18 s/PDF.
Camelot stream 9/12, 4/7, 1, 1,05 s/PDF.
Gemma 3 4B JSON schema: 0/6 στο subset, 3/4 άδειες, 0 errors, 83,06 s/PDF. Μία λάθος υποψήφια τιμή confidence 0,6. Πρόσθετα fallback golden 0/12. Αρχικό JSON run απέτυχε σε 3 PDF· raw λάθος έτος/κλίμακα confidence 0,95.
Κανένα LLM αποτέλεσμα δεν δημοσιεύεται. Λάθος τζίρος χειρότερος από κενό.
Πρόσθετα golden οπτική μεταγραφή agent, χρειάζονται δεύτερο ανθρώπινο έλεγχο.
Camelot/Docling cells με συνθετικές συντεταγμένες, όχι production-ready evidence boxes.
Αναφερμένοι έλεγχοι: 17 passed, 1 skipped στο existing suite, 4 passed scorer. Επιβεβαίωσε πριν το commit.
PyMuPDF χρειάζεται έλεγχο AGPL/commercial license πριν production χρήση.

## Αμέσως επόμενα
1. Ολοκλήρωσε bounded Docling offline install. Προηγούμενη αποτυχία λόγω regex, τώρα SymPy 1.14.0 και regex 2026.9.29 υπάρχουν στο experiments/.wheelhouse/. Adapter do_ocr=False.
2. Ενδεικτικές υπάρχουσες εντολές:
   cd ~/isologismoi
   timeout 120 experiments/.venv-docling/bin/pip install --no-index --no-build-isolation --find-links experiments/.wheelhouse docling pymupdf pdfplumber
   experiments/.venv-docling/bin/python experiments/parsing_benchmark.py --backend docling --timeout 180 --only 54414421000_2024_isologismos
   Χρησιμοποίησε tmux για μακρύ run. Αν παραμείνει blocked γράψε μη μετρημένο, χωρίς επινοημένα αποτελέσματα.
3. Αναγέννησε summary, συμπλήρωσε report placeholders, έλεγξε αναπαραγωγιμότητα και συνοχή denominators. Πρότεινε cron → κοινό υπάρχον Durable Object limiter, parsing mini PC. Μόνο σχέδιο, όχι deploy.
4. Report πρέπει να έχει σύνοψη 5 γραμμών, πλήθη/πηγές, calls/company, πίνακα ημερών ανά σενάριο (1.000, ΑΕ, proxy καταθετών, όλες), benchmark accuracy/refusals/confident wrong/time/cost, crawler, API όρους/GDPR εκπροσώπων, αξία έναντι ICAP/Hellastat/Linked Business και 3 ανοιχτές ερωτήσεις Harold.
5. Τρέξε απαιτούμενους ελέγχους και κάνε τοπικό commit ΜΟΝΟ σχετικών research/experiments αρχείων, όχι push. Παράδωσε σύντομο ελληνικό συμπέρασμα και report path.

Αρχική ανάγνωση που ζήτησε ο Harold: README.md, docs/superpowers/specs/2026-09-03-wayfinder-design.md, worker/src/, extractor/. Χρησιμοποίησε υπάρχοντα τεκμήρια, μην υποθέσεις ότι το handoff υποκαθιστά αρχεία και logs.
