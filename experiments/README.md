# Πειράματα ΓΕΜΗ και parsing — 2026-10-04

Μόνο τοπική έρευνα. Δεν υπάρχει κώδικας deployment ή πρόσβασης σε production D1/secrets. Οι αριθμοί LLM είναι **υποψήφιοι σε quarantine**, όχι δημοσιεύσιμα δεδομένα.

## Αρχεία

| Αρχείο | Χρήση |
|---|---|
| `parsing_benchmark.py` | Απομονωμένες εκτελέσεις ανά PDF, με timeout. Κοινός υπάρχων semantic parser για text/table backends |
| `summarize_benchmark.py` | Επαναβαθμολογεί αποθηκευμένες προβλέψεις και δίνει ακρίβεια ανά πεδίο |
| `fallback-golden.json` | 12 πρόσθετα οπτικά μεταγραμμένα πεδία. Δεν αντικαθιστά τα υπάρχοντα golden |
| `gemi-counts.json`, `compute_scale.py` | Πρωτογενή συγκεντρωτικά πλήθη και υπολογισμοί ημερών |
| `publicity-network-notes.md`, `publicity-evidence/` | Έλεγχος browser, HTTP και κανονικού headless Chrome |
| `publicity_headless.py` | Μία bounded δοκιμή με εφήμερο Chrome profile. Δεν διατηρεί cookies ή raw DOM |
| `geo_extract.py`, `test_geo_extract.py` | Πειραματικό parser: στήλες από γεωμετρία (scope Όμιλος/Εταιρεία, έτος), μονάδα ανά σελίδα, labels σε πολλές γραμμές. Χρησιμοποιεί ξανά labels/money/identities του `extractor/` |
| `fetch_wheels.py` | Βοηθητικό τοπικής εγκατάστασης. Έλεγχος checksum στις νέες λήψεις και resume partial αρχείων |

## Αναπαραγωγή στο mini PC

```bash
cd ~/isologismoi
python3 -m venv experiments/.venv
experiments/.venv/bin/pip install -r experiments/requirements-light.lock
experiments/.venv/bin/python experiments/parsing_benchmark.py --backend pdfplumber
experiments/.venv/bin/python experiments/parsing_benchmark.py --backend pymupdf
experiments/.venv/bin/python experiments/parsing_benchmark.py --backend camelot-stream
experiments/.venv/bin/python experiments/summarize_benchmark.py
python3 experiments/compute_scale.py
PYTHONPATH=extractor experiments/.venv/bin/python -m pytest -q extractor/tests
PYTHONPATH=experiments experiments/.venv/bin/python -m pytest -q experiments/test_benchmark.py
```

Για μακριές εκτελέσεις χρησιμοποιείται tmux. Το benchmark δίνει default timeout 240 s ανά PDF. Δεν κάνει κλήσεις στο ΓΕΜΗ.

Το local vision πείραμα απαιτεί το ήδη διαθέσιμο Ollama model `gemma3:4b` (Q4_K_M). Η εικόνα μένει στο mini PC και στέλνεται μόνο στο localhost. Χρησιμοποιούνται 120 dpi, temperature 0 και σταθερές, χειροκίνητα επιλεγμένες σελίδες. Η επιλογή σελίδων είναι μέρος του πειράματος, **όχι αυτοματοποιημένη λύση εντοπισμού οικονομικών πινάκων**.

```bash
experiments/.venv/bin/python experiments/parsing_benchmark.py \
  --backend gemma3-vision-schema --timeout 400 \
  --only 000306201000_x_6094252 000854801000_2026_xl_ae \
         010033253000_x_5567261 54414421000_2024_isologismos
```

Τα αποτελέσματα αυτής της ημερομηνίας προήλθαν από αρχικά run με `format="json"` και χωριστό run με JSON schema. Δεν συγκρίνονται ως ίδια εκτέλεση. Το αρχικό όριο 700 tokens προκάλεσε και κομμένα JSON. Το schema run είχε όριο 1.200 tokens.

Γεωμετρία στηλών και ελληνικό OCR (RapidOCR 3.9.2 + onnxruntime στο `.venv-docling`, μοντέλο `el_PP-OCRv5_rec_mobile` από modelscope στην πρώτη χρήση):

```bash
experiments/.venv/bin/python experiments/parsing_benchmark.py --backend geo --timeout 120
experiments/.venv-docling/bin/pip install onnxruntime
experiments/.venv-docling/bin/python experiments/parsing_benchmark.py --backend geo-ocr --timeout 400
PYTHONPATH=experiments experiments/.venv/bin/python -m pytest -q experiments/test_geo_extract.py
```

Το `geo-ocr` κάνει OCR μόνο σε σελίδες με λιγότερους από 300 χαρακτήρες, έως 40 σελίδες/PDF, στα 200 dpi. Οι κανόνες αναπτύχθηκαν πάνω στα ίδια fixtures: τα αποτελέσματα είναι in-sample.

## Τι ακριβώς συγκρίνεται

pdfplumber: ο υπάρχων extractor. PyMuPDF: πραγματικές λέξεις/συντεταγμένες αντί για pdfplumber, με **ίδιους ελέγχους και labels**. Camelot stream και Docling: τα cells των πινάκων τροφοδοτούν τον ίδιο parser, με συνθετικές συντεταγμένες για τη διάταξη γραμμής/στήλης και το αρχικό κείμενο σελίδας για τα document facts. Οι συνθετικές συντεταγμένες **δεν είναι έγκυρα production evidence boxes**. Δεν πρόκειται για ανεξάρτητους ολοκληρωμένους financial parsers ή αξιολόγηση όλων των δυνατοτήτων των εργαλείων.

Το Docling adapter έχει `do_ocr=False`, CPU και δύο threads. Αυτή η παραλλαγή ελέγχει layout/table extraction σε text PDFs. Δεν αξιολογεί Greek OCR. Για Docling απαιτείται χωριστό περιβάλλον και μοντέλα που μπορεί να ληφθούν στην πρώτη εκτέλεση:

```bash
python3 -m venv experiments/.venv-docling
experiments/.venv-docling/bin/pip install torch torchvision \
  --index-url https://download.pytorch.org/whl/cpu
experiments/.venv-docling/bin/pip install docling pdfplumber pymupdf
experiments/.venv-docling/bin/python experiments/parsing_benchmark.py \
  --backend docling --timeout 180 --only 54414421000_2024_isologismos
```

Offline παραλλαγή που χρησιμοποιήθηκε στις 2026-10-05 (wheels στο `experiments/.wheelhouse/`, docling 2.133.0, torch 2.14.1+cpu). Τα μοντέλα κατεβαίνουν από Hugging Face στην πρώτη εκτέλεση:

```bash
timeout 300 experiments/.venv-docling/bin/pip install --no-index --no-build-isolation \
  --find-links experiments/.wheelhouse docling pymupdf pdfplumber
experiments/.venv-docling/bin/python experiments/parsing_benchmark.py --backend docling --timeout 400
```

API verification: DeepWiki attempts failed, Context7 confirmed PyMuPDF/Docling APIs, official Camelot quickstart and Docling example were read. Current table JSON fields were also checked in the downloaded docling-core source. Sources: [PyMuPDF Page](https://pymupdf.readthedocs.io/en/latest/page.html), [Camelot quickstart](https://camelot-py.readthedocs.io/en/latest/user/quickstart.html), [Docling example](https://github.com/docling-project/docling/blob/main/docs/examples/custom_convert.py), [Ollama generate](https://docs.ollama.com/api/generate).

## Μετρικές και όρια

Απόλυτη ανοχή: 0,005 EUR. Η αριθμητική ισότητα είναι χωριστή από την **αγκυρωμένη ισότητα**, που απαιτεί σωστό έτος/νόμισμα/μονάδα και, στα συμπληρωματικά golden, company scope. Απούσα τιμή δεν είναι μηδέν. Μη αριθμητικό decimal string απορρίπτεται. Επιπλέον πεδία στα παλιά refusal golden είναι unsupported/policy violations, όχι αυτομάτως αποδεδειγμένα λανθασμένα ποσά.

Το `summary.json` ξεχωρίζει άδεια έξοδο από exception/timeout. Ένα τεχνικό σφάλμα δεν προσμετράται ως σωστή άρνηση. Σφάλματα, καθυστερήσεις πρώτης χρήσης και διαφορετικός αριθμός επιλεγμένων LLM σελίδων περιορίζουν τις συγκρίσεις χρόνου. Το κόστος API είναι μηδέν, αλλά δεν μετρήθηκαν ηλεκτρική ενέργεια ή απόσβεση εξοπλισμού.

Το corpus έχει έξι πραγματικά PDF, μόνο δύο με υπάρχουσες ελεγμένες τιμές, και ένα synthetic blank PDF. Δεν είναι αντιπροσωπευτικό δείγμα της χώρας. Τα συμπληρωματικά golden χρειάζονται δεύτερο ανθρώπινο έλεγχο. Δεν άλλαξαν `extractor/`, `worker/` ή `data/`.

Μην επαναλαμβάνεις probes της δημόσιας ιστοσελίδας μετά από 429. Δεν υπάρχει rotation IP/cookies, CAPTCHA bypass ή αποθήκευση tokens. Οι δύο αποτυχημένες αναθέσεις OpenCode αναφέρονται στα network notes.

