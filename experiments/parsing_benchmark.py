#!/usr/bin/env python3
"""Offline extraction benchmark. No production reads or writes.
Layout engines share the existing semantic extractor. LLM output is quarantine only.
"""
import argparse, base64, importlib, json, os, statistics, subprocess, sys, time, urllib.request
from decimal import Decimal, InvalidOperation
from pathlib import Path
from unittest.mock import patch
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "extractor"))
semantic = importlib.import_module("wayfinder_extract.extract")
OUT = ROOT / "experiments/results"
OUT.mkdir(exist_ok=True)

class Page:
    def __init__(self, width, height, text, words):
        self.width, self.height, self.text, self.words = width, height, text, words
    def extract_words(self, **kwargs): return self.words
    def extract_text(self): return self.text
class Document:
    def __init__(self, pages): self.pages = pages
    def __enter__(self): return self
    def __exit__(self, *args): pass

def word(text, x0, y0, x1, y1):
    return dict(text=text,x0=float(x0),top=float(y0),x1=float(x1),bottom=float(y1))

def pymupdf_pages(path):
    import pymupdf
    with pymupdf.open(path) as doc:
        return [Page(p.rect.width,p.rect.height,p.get_text(),
                     [word(w[4],*w[:4]) for w in p.get_text("words")]) for p in doc]

def table_words(rows, top=0):
    # Synthetic coordinates preserve row and column order, not PDF provenance.
    words=[]
    for i,row in enumerate(rows):
        for j,cell in enumerate(row):
            tokens=str(cell).replace("\n"," ").split()
            for k,t in enumerate(tokens):
                x=j*500+k*15
                words.append(word(t,x,top+i*9,x+12,top+i*9+6))
    return words

def backend(path, name):
    if name=="pdfplumber": return semantic.extract(path.read_bytes())
    pages=pymupdf_pages(path)
    if name=="camelot-stream":
        import camelot
        tables=camelot.read_pdf(str(path),pages="all",flavor="stream")
        for p in pages: p.words=[]
        offsets={}
        for table in tables:
            idx=int(table.page)-1
            top=offsets.get(idx,0)
            pages[idx].words.extend(table_words(table.df.values.tolist(),top))
            offsets[idx]=top+(len(table.df)+3)*9
    if name=="docling":
        from docling.datamodel.accelerator_options import AcceleratorDevice, AcceleratorOptions
        from docling.datamodel.base_models import InputFormat
        from docling.datamodel.pipeline_options import PdfPipelineOptions
        from docling.document_converter import DocumentConverter, PdfFormatOption
        options=PdfPipelineOptions()
        options.do_ocr=False
        options.accelerator_options=AcceleratorOptions(num_threads=2,device=AcceleratorDevice.CPU)
        converter=DocumentConverter(format_options={InputFormat.PDF:PdfFormatOption(pipeline_options=options)})
        data=converter.convert(path).document.export_to_dict()
        (OUT/(path.stem+".docling.json")).write_text(json.dumps(data,ensure_ascii=False,default=str))
        for p in pages: p.words=[]
        offsets={}
        for table in data.get("tables",[]):
            prov=table.get("prov",[])
            if not prov: continue
            idx=prov[0]["page_no"]-1
            if idx>=len(pages):continue
            td=table["data"]
            rows=[[""]*td["num_cols"] for _ in range(td["num_rows"])]
            for c in td.get("table_cells",[]):
                rows[c["start_row_offset_idx"]][c["start_col_offset_idx"]]=c.get("text","")
            top=offsets.get(idx,0)
            pages[idx].words.extend(table_words(rows,top))
            offsets[idx]=top+(len(rows)+3)*9
    with patch.object(semantic.pdfplumber,"open",return_value=Document(pages)):
        return semantic.extract(path.read_bytes())

def score(gold, got):
    expected=gold.get("figures",{})
    actual=got.get("figures",{})
    correct=[]; wrong=[]; missing=[]
    for key,exp in expected.items():
        if key not in actual: missing.append(key);continue
        try: match=abs(Decimal(str(actual[key]["value"]))-Decimal(str(exp["value"])))<=Decimal("0.005")
        except (KeyError,TypeError,InvalidOperation):match=False
        (correct if match else wrong).append(key)
    extras=sorted(set(actual)-set(expected))
    context_match=all(gold.get(k)==got.get(k) for k in ["fiscal_year","currency","unit_multiplier"])
    if "scope" in gold:context_match=context_match and gold["scope"]==got.get("scope")
    anchored=len(correct) if context_match else 0
    return dict(expected_fields=len(expected),correct_fields=len(correct),anchored_correct_fields=anchored,context_match=context_match,wrong_fields=wrong,
                missing_fields=missing,unsupported_fields=extras,
                status_match=gold["status"]==got.get("status"),
                reason_match=gold.get("reason")==got.get("reason"),
                metadata_match=all(gold.get(k)==got.get(k) for k in ["ar_gemi","fiscal_year","currency","unit_multiplier"]),
                refusal=not bool(actual),policy_violation=gold["status"]=="unparseable" and bool(actual))

LLM_PROMPT = """Read the financial statement in this page image. Return JSON only.
Never guess. Use company-only current-year column, never consolidated group or prior year.
Return {"status":"needs_review","fiscal_year":null,"scope":null,"currency":"EUR",
"unit_multiplier":1,"figures":{},"reason":"..."}. If legible, figures may contain
turnover, total_assets, equity, pre_tax_profit, net_profit.
Each figure must be {"value":"decimal in full EUR units","raw_text":"literal amount",
"label":"literal row label","confidence":0.0}. Identify year, scope and multiplier.
Use null or omit a field if ambiguous. This is quarantine, not published output.
"""
LLM_SCHEMA = {'type': 'object', 'properties': {'status': {'type': 'string', 'enum': ['needs_review']}, 'fiscal_year': {'type': ['integer', 'null']}, 'scope': {'type': ['string', 'null'], 'enum': ['company', 'group', None]}, 'currency': {'type': 'string', 'enum': ['EUR']}, 'unit_multiplier': {'type': 'integer', 'enum': [1, 1000]}, 'reason': {'type': 'string'}, 'figures': {'type': 'object', 'properties': {'turnover': {'type': 'object', 'properties': {'value': {'type': 'string'}, 'raw_text': {'type': 'string'}, 'label': {'type': 'string'}, 'confidence': {'type': 'number'}}, 'required': ['value', 'raw_text', 'label', 'confidence'], 'additionalProperties': False}, 'total_assets': {'type': 'object', 'properties': {'value': {'type': 'string'}, 'raw_text': {'type': 'string'}, 'label': {'type': 'string'}, 'confidence': {'type': 'number'}}, 'required': ['value', 'raw_text', 'label', 'confidence'], 'additionalProperties': False}, 'equity': {'type': 'object', 'properties': {'value': {'type': 'string'}, 'raw_text': {'type': 'string'}, 'label': {'type': 'string'}, 'confidence': {'type': 'number'}}, 'required': ['value', 'raw_text', 'label', 'confidence'], 'additionalProperties': False}, 'pre_tax_profit': {'type': 'object', 'properties': {'value': {'type': 'string'}, 'raw_text': {'type': 'string'}, 'label': {'type': 'string'}, 'confidence': {'type': 'number'}}, 'required': ['value', 'raw_text', 'label', 'confidence'], 'additionalProperties': False}, 'net_profit': {'type': 'object', 'properties': {'value': {'type': 'string'}, 'raw_text': {'type': 'string'}, 'label': {'type': 'string'}, 'confidence': {'type': 'number'}}, 'required': ['value', 'raw_text', 'label', 'confidence'], 'additionalProperties': False}}, 'additionalProperties': False}}, 'required': ['status', 'fiscal_year', 'scope', 'currency', 'unit_multiplier', 'figures', 'reason'], 'additionalProperties': False}

def llm(path, strict=False):
    import pymupdf
    # Fixed page choices, declared before LLM; bounded to <=3 pages/PDF.
    selections={
      "54414421000_2024_isologismos":[2,3],
      "026496140000_x_5504505":[8,9,10],
      "010033253000_x_5567261":[22,23,24],
      "000306201000_x_6094252":[14],
      "000854801000_2026_xl_ae":[13,14],
      "113772252000_2026_mid_ae":[1],
      "_synthetic_no_text":[1]}
    records=[]
    with pymupdf.open(path) as doc:
        for number in selections[path.stem]:
            if number>len(doc):continue
            png=doc[number-1].get_pixmap(dpi=120).tobytes("png")
            payload=dict(model="gemma3:4b",prompt=LLM_PROMPT,images=[base64.b64encode(png).decode()],
                         format=LLM_SCHEMA if strict else "json",stream=False,options=dict(temperature=0,num_predict=1200 if strict else 700,num_ctx=4096),
                         keep_alive="5m")
            request=urllib.request.Request("http://127.0.0.1:11434/api/generate",
                       data=json.dumps(payload).encode(),headers={"Content-Type":"application/json"})
            start=time.perf_counter()
            with urllib.request.urlopen(request,timeout=180) as response:r=json.load(response)
            candidate=json.loads(r["response"])
            if not isinstance(candidate.get("figures",{}),dict):
                if strict:raise ValueError("invalid figures schema")
            records.append(dict(page=number,seconds=time.perf_counter()-start,candidate=candidate,
                                prompt_tokens=r.get("prompt_eval_count"),output_tokens=r.get("eval_count"),
                                done_reason=r.get("done_reason")))
    (OUT/(path.stem+(".gemma3-schema-pages.json" if strict else ".gemma3-pages.json"))).write_text(json.dumps(records,ensure_ascii=False,indent=2))
    # A conflicting candidate is omitted. No automatic publication.
    merged={};conflicts=set();metadata={}
    for r in records:
        c=r["candidate"]
        for k in ["fiscal_year","scope","unit_multiplier","currency"]:
            if c.get(k) is not None:metadata.setdefault(k,c[k])
        for key,f in c.get("figures",{}).items():
            if not isinstance(f,dict) or f.get("value") is None:continue
            f=dict(f,page=r["page"],source="llm_quarantine")
            if key in merged and str(merged[key]["value"])!=str(f["value"]):conflicts.add(key)
            else:merged[key]=f
    for k in conflicts:merged.pop(k,None)
    return dict(status="needs_review",reason="llm_quarantine",figures=merged,**metadata)

def run_one(path,name):
    gold_path=path.with_suffix(".golden.json")
    gold=json.loads(gold_path.read_text()) if gold_path.exists() else dict(status="unparseable",reason="no_text_layer",figures={},ar_gemi=None,fiscal_year=None,currency="EUR",unit_multiplier=1)
    started=time.perf_counter()
    try:
        got=llm(path,strict=name.endswith("schema")) if name.startswith("gemma3") else backend(path,name)
        metrics=score(gold,got)
        metrics["confident_wrong_fields"]=[k for k in metrics["wrong_fields"] if not name.startswith("gemma3") or float(got["figures"][k].get("confidence",0))>=0.9]
        supplemental=json.loads((ROOT/"experiments/fallback-golden.json").read_text()).get(path.stem)
        fallback_metrics=None
        if supplemental:
            fallback_metrics=score(dict(status="needs_review",**supplemental),got)
            fallback_metrics["forbidden_emissions"]=[k for k in supplemental["must_omit"] if k in got["figures"]]
            fallback_metrics["confident_wrong_fields"]=[k for k in fallback_metrics["wrong_fields"] if not name.startswith("gemma3") or float(got["figures"][k].get("confidence",0))>=0.9]
        return dict(pdf=path.name,backend=name,seconds=time.perf_counter()-started,
                    api_cost_eur=0,prediction=got,metrics=metrics,fallback_metrics=fallback_metrics,error=None)
    except Exception as e:
        return dict(pdf=path.name,backend=name,seconds=time.perf_counter()-started,
                    api_cost_eur=0,prediction=None,metrics=None,error=type(e).__name__+": "+str(e)[:400])

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--backend",choices=["pdfplumber","pymupdf","camelot-stream","docling","gemma3-vision","gemma3-vision-schema"])
    ap.add_argument("--pdf")
    ap.add_argument("--only",nargs="*")
    ap.add_argument("--timeout",type=int,default=240)
    args=ap.parse_args()
    if args.pdf:
        result=run_one(Path(args.pdf),args.backend)
        print(json.dumps(result,ensure_ascii=False,default=str));return
    files=sorted((ROOT/"extractor/fixtures").glob("*.pdf"))
    if args.only:files=[p for p in files if p.stem in args.only]
    for path in files:
        target=OUT/(args.backend+"--"+path.stem+".json")
        cmd=[sys.executable,__file__,"--backend",args.backend,"--pdf",str(path)]
        started=time.perf_counter()
        try:
            proc=subprocess.run(cmd,capture_output=True,text=True,timeout=args.timeout,
                     env=dict(os.environ,OMP_NUM_THREADS="2",OPENBLAS_NUM_THREADS="2",TOKENIZERS_PARALLELISM="false"))
            if proc.returncode: raise RuntimeError(proc.stderr[-500:])
            result=json.loads(proc.stdout.strip().splitlines()[-1])
        except Exception as e:
            result=dict(pdf=path.name,backend=args.backend,seconds=time.perf_counter()-started,
                        api_cost_eur=0,prediction=None,metrics=None,error=str(e)[:500])
        target.write_text(json.dumps(result,ensure_ascii=False,indent=2,default=str))
        print(path.name,args.backend,round(result["seconds"],2),result["error"],flush=True)
if __name__=="__main__":main()

