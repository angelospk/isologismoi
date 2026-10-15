#!/usr/bin/env python3
"""Greek OCR text quality on the same scans: marker/surya vs PP-OCRv5 vs Tesseract.

Truth for the 4 synthetic scans is the text layer of the original pages
(ocr_compare.make_scan dropped it). Tokens are compared as multisets, so the
reading order of an engine does not count. For the real TITAN scan there is no
text truth: the check is whether the fallback-golden amounts appear verbatim.
  text  --engine paddle|tesseract|marker  -> results/ocr-text-<engine>.json
  score                                   -> results/ocr-quality.json
  fields                                  -> results/ocr-compare-marker.json (same 24 fields as ocr_compare.py)
Engines need their own venv: paddle .venv-docling, marker .venv-marker.
"""
import argparse, json, re, subprocess, sys, tempfile, time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "experiments"))
import parsing_benchmark as pb  # noqa: E402
from ocr_compare import SYNTHETIC, WORK, FIX, SUPP, expected  # noqa: E402

REAL = "000854801000_2026_xl_ae"
NUM = re.compile(r"[-−(]?\s?\d[\d.,]*\d(?:\s?\))?")
GREEK = re.compile(r"[α-ωάέήίόύώϊϋΐΰς]{4,}")


def scans():
    out = {f"{stem}__scan": WORK / f"{stem}__scan.pdf" for stem in SYNTHETIC}
    out[REAL] = FIX / f"{REAL}.pdf"
    return out


def page_count(path):
    import pymupdf
    with pymupdf.open(path) as doc:
        return len(doc)


def ocr_text(engine, path):
    import pymupdf
    if engine == "paddle":
        return [" ".join(w["text"] for w in pb.ocr_words(path, i)) for i in range(page_count(path))]
    if engine == "tesseract":
        with tempfile.TemporaryDirectory() as tmp:
            ocrd = Path(tmp) / "ocr.pdf"
            subprocess.run(["ocrmypdf", "-q", "-l", "ell+eng", "--skip-text", "--optimize", "0",
                            "--invalidate-digital-signatures", "--output-type", "pdf", "-j", "4",
                            str(path), str(ocrd)], check=True, timeout=1800)
            with pymupdf.open(ocrd) as doc:
                return [p.get_text() for p in doc]
    if engine == "marker":
        saved = pb.OUT / f"{path.stem}.marker-ocr.json"
        data = json.loads(saved.read_text()) if saved.exists() else pb.marker_json(path, True, True)
        return pb.marker_page_texts(data, page_count(path))
    raise ValueError(engine)


def truth_text(stem):
    import pymupdf
    pages = SYNTHETIC[stem]
    with pymupdf.open(FIX / f"{stem}.pdf") as doc:
        return [doc[n - 1].get_text() for n in (pages or range(1, len(doc) + 1))]


def overlap(truth, got):
    hit = sum((truth & got).values())
    return dict(truth=sum(truth.values()), got=sum(got.values()), hit=hit,
                recall=round(hit / max(sum(truth.values()), 1), 4),
                precision=round(hit / max(sum(got.values()), 1), 4))


def signed(token):
    """'(1.234)' and '-1.234' are the same negative amount; the sign counts."""
    token = "".join(token.split())
    neg = token[0] in "-−(" and (token[0] != "(" or token.endswith(")"))
    core = token.strip("-−()")
    return ("-" if neg else "") + core


def numbers(text):
    return Counter(signed(t) for t in NUM.findall(text) if sum(c.isdigit() for c in t) >= 3)


def words(text):
    return Counter(GREEK.findall(text.lower()))


def greek_amount(v):
    return f"{int(v):,}".replace(",", ".")


def score():
    rows = []
    for engine in ("paddle", "tesseract", "marker"):
        path = pb.OUT / f"ocr-text-{engine}.json"
        if not path.exists():
            continue
        saved = json.loads(path.read_text())
        for doc, r in saved.items():
            text = " ".join(r["pages"]) if r.get("pages") else ""
            row = dict(engine=engine, doc=doc, seconds=r["seconds"], error=r.get("error"))
            if doc == REAL:
                amounts = {k: greek_amount(v["value"]) for k, v in SUPP[REAL]["figures"].items()}
                tokens = set(numbers(text))
                row["amounts_verbatim"] = {k: a in tokens or a + ",00" in tokens for k, a in amounts.items()}
            else:
                truth = " ".join(truth_text(doc.removesuffix("__scan")))
                row["numbers"] = overlap(numbers(truth), numbers(text))
                row["greek_words"] = overlap(words(truth), words(text))
            rows.append(row)
    (pb.OUT / "ocr-quality.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2))
    for engine in ("paddle", "tesseract", "marker"):
        sel = [r for r in rows if r["engine"] == engine]
        if not sel:
            continue
        syn = [r for r in sel if "numbers" in r]
        agg = lambda key, part: sum(r[key][part] for r in syn)
        real = [r for r in sel if "amounts_verbatim" in r]
        found = sum(sum(r["amounts_verbatim"].values()) for r in real)
        print(f"{engine:9} numbers recall {agg('numbers', 'hit')}/{agg('numbers', 'truth')} "
              f"precision {agg('numbers', 'hit')}/{agg('numbers', 'got')} | greek words recall "
              f"{agg('greek_words', 'hit')}/{agg('greek_words', 'truth')} | TITAN amounts {found}/4 | "
              f"errors {sum(bool(r['error']) for r in sel)} | seconds {round(sum(r['seconds'] for r in sel), 1)}")


def fields():
    """marker OCR -> geo_extract, scored like ocr_compare.py. Needs the saved marker-ocr JSON."""
    rows = []
    for doc, path in scans().items():
        stem = doc.removesuffix("__scan")
        saved = pb.OUT / f"{path.stem}.marker-ocr.json"
        gold = expected(stem)
        if not saved.exists():
            rows.append(dict(pdf=stem, engine="marker", expected=len(gold["figures"]), anchored=0, wrong=[],
                             forbidden=[], error="no marker-ocr JSON (not measured)"))
            continue
        got = pb.marker_extract(path, json.loads(saved.read_text()), use_geo=True, ocr=True)
        m = pb.score(gold, got)
        rows.append(dict(pdf=stem, kind="real" if doc == REAL else "synthetic", engine="marker",
                         expected=m["expected_fields"], anchored=m["anchored_correct_fields"],
                         wrong=m["wrong_fields"], missing=m["missing_fields"], context_match=m["context_match"],
                         forbidden=[k for k in gold.get("must_omit", []) if k in got.get("figures", {})],
                         values={k: v["value"] for k, v in got.get("figures", {}).items()},
                         reason=got.get("reason"), notes=got.get("notes", [])[:40], error=None))
        r = rows[-1]
        print(f'{stem[:24]:24} {r["anchored"]}/{r["expected"]} wrong={r["wrong"]} forbidden={r["forbidden"]} {r["reason"] or ""}')
    (pb.OUT / "ocr-compare-marker.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2))
    print("marker anchored", sum(r["anchored"] for r in rows), "/", sum(r["expected"] for r in rows),
          "wrong", sum(len(r["wrong"]) for r in rows), "forbidden", sum(len(r["forbidden"]) for r in rows),
          "not measured docs", sum(bool(r["error"]) for r in rows))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["text", "score", "fields"])
    ap.add_argument("--engine", choices=["paddle", "tesseract", "marker"])
    args = ap.parse_args()
    if args.cmd == "score":
        return score()
    if args.cmd == "fields":
        return fields()
    out = {}
    for doc, path in scans().items():
        started = time.perf_counter()
        try:
            out[doc] = dict(pages=ocr_text(args.engine, path), error=None)
        except Exception as e:  # an engine failure is not empty text
            out[doc] = dict(pages=None, error=f"{type(e).__name__}: {str(e)[:300]}")
        out[doc]["seconds"] = round(time.perf_counter() - started, 1)
        print(doc, args.engine, out[doc]["seconds"], out[doc]["error"], flush=True)
    (pb.OUT / f"ocr-text-{args.engine}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
