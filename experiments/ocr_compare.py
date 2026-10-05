#!/usr/bin/env python3
"""Compare Greek OCR engines under the same geo parser. Local only; no GEMI calls.

Scans with known answers: the one real scan (TITAN) plus synthetic scans made
from text-layer fixtures. A synthetic scan renders selected pages at 150 dpi,
adds noise and JPEG artefacts, and drops the text layer, so the expected
figures are the existing golden values. Engines:
  paddle    RapidOCR, PP-OCRv5 det + Greek rec (geo-ocr backend)
  tesseract OCRmyPDF + Tesseract 5 'ell+eng', then the PDF text layer
"""
import io, json, subprocess, sys, tempfile, time
from pathlib import Path
import numpy as np
import pymupdf
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "experiments"))
import parsing_benchmark as pb  # noqa: E402

FIX = ROOT / "extractor/fixtures"
WORK = ROOT / "experiments/synthetic-scans"
OUT = ROOT / "experiments/results/ocr-compare.json"
SUPP = json.loads((ROOT / "experiments/fallback-golden.json").read_text())

# stem -> pages kept in the synthetic scan (1-based). Page 1 carries the filing's facts.
SYNTHETIC = {
    "54414421000_2024_isologismos": None,          # whole document
    "026496140000_x_5504505": [1, 8, 9, 10],
    "000306201000_x_6094252": [1, 14, 15, 16],
    "010033253000_x_5567261": [1, 22, 23, 24],
}
REAL_SCANS = ["000854801000_2026_xl_ae"]


def expected(stem):
    gold = json.loads((FIX / f"{stem}.golden.json").read_text())
    if gold["figures"]:
        return gold
    return dict(status="needs_review", **SUPP[stem])


def make_scan(stem, pages, seed=0):
    rng = np.random.default_rng(seed)
    src = pymupdf.open(FIX / f"{stem}.pdf")
    out = pymupdf.open()
    for n in pages or range(1, len(src) + 1):
        page = src[n - 1]
        pix = page.get_pixmap(dpi=150, colorspace=pymupdf.csGRAY)
        img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.h, pix.w).astype(np.int16)
        img = np.clip(img + rng.normal(0, 12, img.shape), 0, 255).astype(np.uint8)
        buf = io.BytesIO()
        Image.fromarray(img).rotate(0.4, fillcolor=255).save(buf, "JPEG", quality=60)
        new = out.new_page(width=page.rect.width, height=page.rect.height)
        new.insert_image(new.rect, stream=buf.getvalue())
    WORK.mkdir(exist_ok=True)
    target = WORK / f"{stem}__scan.pdf"
    out.save(target)
    return target


def run_paddle(path):
    return pb.geo(path, ocr=True)


def run_tesseract(path):
    with tempfile.TemporaryDirectory() as tmp:
        ocrd = Path(tmp) / "ocr.pdf"
        subprocess.run(["ocrmypdf", "-q", "-l", "ell+eng", "--skip-text", "--optimize", "0", "--invalidate-digital-signatures",
                        "--output-type", "pdf", "-j", "4", str(path), str(ocrd)],
                       check=True, timeout=900)
        return pb.geo(ocrd, ocr=False)


def main():
    cases = [(stem, make_scan(stem, pages), "synthetic") for stem, pages in SYNTHETIC.items()]
    cases += [(stem, FIX / f"{stem}.pdf", "real") for stem in REAL_SCANS]
    rows = []
    for stem, path, kind in cases:
        gold = expected(stem)
        for engine, fn in [("paddle", run_paddle), ("tesseract", run_tesseract)]:
            started = time.perf_counter()
            try:
                got, error = fn(path), None
            except Exception as e:  # an engine failure is not a refusal
                got, error = dict(figures={}), f"{type(e).__name__}: {str(e)[:300]}"
            m = pb.score(gold, got)
            must_omit = [k for k in gold.get("must_omit", []) if k in got.get("figures", {})]
            rows.append(dict(pdf=stem, kind=kind, engine=engine, seconds=round(time.perf_counter() - started, 2),
                             expected=m["expected_fields"], anchored=m["anchored_correct_fields"],
                             wrong=m["wrong_fields"], missing=m["missing_fields"], forbidden=must_omit,
                             context_match=m["context_match"], error=error,
                             values={k: v["value"] for k, v in got.get("figures", {}).items()},
                             notes=got.get("notes", [])[:40]))
            r = rows[-1]
            print(f'{stem[:24]:24} {kind:9} {engine:9} {r["anchored"]}/{r["expected"]} wrong={r["wrong"]} '
                  f'forbidden={must_omit} {r["seconds"]}s {error or ""}', flush=True)
    OUT.write_text(json.dumps(rows, ensure_ascii=False, indent=2))
    for engine in ("paddle", "tesseract"):
        sel = [r for r in rows if r["engine"] == engine]
        print(engine, "anchored", sum(r["anchored"] for r in sel), "/", sum(r["expected"] for r in sel),
              "wrong", sum(len(r["wrong"]) for r in sel), "forbidden", sum(len(r["forbidden"]) for r in sel),
              "errors", sum(bool(r["error"]) for r in sel), "seconds", round(sum(r["seconds"] for r in sel), 1))


if __name__ == "__main__":
    main()
