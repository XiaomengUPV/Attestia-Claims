"""
Attestia Claims — API backend
==============================
FastAPI service powering the Attestia Claims fraud-review console.

Replaces the earlier Streamlit demo with a REST API + static single-page
frontend (static/index.html). Same detection stack underneath:

    1. Rule engine   (rule_checks.RuleEngine)   — deterministic checks
    2. LLM reasoning (llm_checker.LLMChecker)   — Claude, if API key is set
    3. Decision policy shared with fraud_engine.ACCEPTED_LLM_CONFIDENCE

Run:
    python src/api.py
    -> http://localhost:8600
"""

import json
import os
import sys
import tempfile
from pathlib import Path

from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

BASE_DIR   = Path(__file__).resolve().parent.parent
SRC_DIR    = BASE_DIR / "src"
STATIC_DIR = BASE_DIR / "static"
CLAIMS_JSON = BASE_DIR / "data" / "raw_claims" / "claims.json"
METRICS_JSON = BASE_DIR / "reports" / "metrics.json"
NCCI_PATH  = BASE_DIR / "data" / "ncci_edits.xlsx"

sys.path.insert(0, str(SRC_DIR))

from rule_checks import RuleEngine                      # noqa: E402
from parse_edi import parse_edi_file                    # noqa: E402

try:
    from fraud_engine import ACCEPTED_LLM_CONFIDENCE    # single source of truth
except ImportError:
    ACCEPTED_LLM_CONFIDENCE = ("high",)

try:
    from llm_checker import LLMChecker
    LLM_IMPORTABLE = True
except ImportError:
    LLM_IMPORTABLE = False

app = FastAPI(title="Attestia Claims", version="1.0")

# ── Loaded once at startup ─────────────────────────────────────────────────────
STATE = {"claims": [], "by_id": {}, "engine": None, "llm": None}


@app.on_event("startup")
def startup():
    if CLAIMS_JSON.exists():
        STATE["claims"] = json.loads(CLAIMS_JSON.read_text(encoding="utf-8"))
        STATE["by_id"] = {c["claim_id"]: c for c in STATE["claims"]}
    print(f"  Claims loaded: {len(STATE['claims'])}")
    print("  Loading rule engine (NCCI table takes ~30s)...")
    STATE["engine"] = RuleEngine(ncci_path=NCCI_PATH)
    if LLM_IMPORTABLE and os.environ.get("ANTHROPIC_API_KEY"):
        try:
            STATE["llm"] = LLMChecker()
            print("  LLM reasoning: enabled")
        except Exception as e:
            print(f"  LLM reasoning: unavailable ({e})")
    else:
        print("  LLM reasoning: disabled (set ANTHROPIC_API_KEY to enable)")


# ── Decision logic (mirrors fraud_engine) ──────────────────────────────────────
def adjudicate(claim):
    """Run rules, then LLM if needed; apply the shared confidence policy."""
    rule = STATE["engine"].check(claim) if STATE["engine"] else None

    if rule and rule.get("fraud_detected"):
        return {
            "fraud_detected": True,
            "fraud_type": rule.get("fraud_type"),
            "confidence": "high",
            "explanation": rule.get("explanation", ""),
            "engine": "rule_engine",
        }, rule, None

    llm = None
    if STATE["llm"]:
        try:
            llm = STATE["llm"].check(claim)
        except Exception as e:
            llm = {"fraud_detected": False, "confidence": "low",
                   "explanation": f"LLM check failed: {e}", "error": True}

    if llm and llm.get("fraud_detected") and \
            llm.get("confidence", "low") in ACCEPTED_LLM_CONFIDENCE:
        return {
            "fraud_detected": True,
            "fraud_type": llm.get("fraud_type"),
            "confidence": llm.get("confidence"),
            "explanation": llm.get("explanation", ""),
            "engine": "llm_claude",
        }, rule, llm

    note = ("All checks passed. No fraud indicators detected."
            if STATE["llm"] else
            "Rule checks passed. AI reasoning is off — set ANTHROPIC_API_KEY "
            "for the full analysis.")
    if llm and llm.get("fraud_detected"):
        note = (f"AI raised a {llm.get('confidence')}-confidence concern, below "
                f"the current decision threshold. Claim is cleared; see AI notes.")
    return {"fraud_detected": False, "fraud_type": None, "confidence": "high",
            "explanation": note, "engine": "combined"}, rule, llm


# ── API routes ────────────────────────────────────────────────────────────────
@app.get("/api/meta")
def meta():
    types = sorted({c["fraud_type"] for c in STATE["claims"]})
    metrics = None
    if METRICS_JSON.exists():
        try:
            m = json.loads(METRICS_JSON.read_text(encoding="utf-8"))
            b = m.get("binary", {})
            metrics = {"f1": b.get("f1"), "precision": b.get("precision"),
                       "recall": b.get("recall")}
        except Exception:
            pass
    return {
        "app": "Attestia Claims",
        "claims_loaded": len(STATE["claims"]),
        "fraud_types": types,
        "rule_engine": STATE["engine"] is not None,
        "llm_enabled": STATE["llm"] is not None,
        "confidence_policy": list(ACCEPTED_LLM_CONFIDENCE),
        "metrics": metrics,
    }


@app.get("/api/claims")
def claims(search: str = "", ftype: str = "", offset: int = 0, limit: int = 40):
    rows = STATE["claims"]
    if ftype:
        rows = [c for c in rows if c["fraud_type"] == ftype]
    if search:
        q = search.lower()
        rows = [c for c in rows if q in c["claim_id"].lower()
                or q in str(c.get("patient", "")).lower()
                or q in str(c.get("provider", "")).lower()
                or any(q in code.lower() for code in c["procedure_codes"])]
    total = len(rows)
    rows = rows[offset:offset + limit]
    slim = [{
        "claim_id": c["claim_id"], "date": c["date"],
        "patient": (c.get("patient") or {}).get("name", "") if isinstance(c.get("patient"), dict) else c.get("patient", ""),
        "provider": (c.get("provider") or {}).get("name", "") if isinstance(c.get("provider"), dict) else c.get("provider", ""),
        "codes": c["procedure_codes"], "total": c["total_charge"],
        "label": c["fraud_type"],
    } for c in rows]
    return {"total": total, "rows": slim}


@app.get("/api/claims/{claim_id}")
def claim_detail(claim_id: str):
    c = STATE["by_id"].get(claim_id)
    if not c:
        raise HTTPException(404, f"Claim {claim_id} not found")
    return c


@app.post("/api/analyze/{claim_id}")
def analyze(claim_id: str):
    c = STATE["by_id"].get(claim_id)
    if not c:
        raise HTTPException(404, f"Claim {claim_id} not found")
    verdict, rule, llm = adjudicate(c)
    return {"claim_id": claim_id, "verdict": verdict,
            "rule_result": rule, "llm_result": llm}


@app.post("/api/upload")
async def upload(file: UploadFile = File(...)):
    if not file.filename.lower().endswith(".edi"):
        raise HTTPException(400, "Upload an EDI 837P file (.edi). PDF intake "
                                 "runs through the batch OCR pipeline.")
    raw = await file.read()
    with tempfile.NamedTemporaryFile(suffix=".edi", delete=False, mode="wb") as tmp:
        tmp.write(raw)
        tmp_path = Path(tmp.name)
    try:
        claim = parse_edi_file(tmp_path)
    finally:
        tmp_path.unlink(missing_ok=True)
    if not claim:
        raise HTTPException(422, "Could not parse this file as EDI 837P.")
    verdict, rule, llm = adjudicate(claim)
    return {"claim": claim, "verdict": verdict,
            "rule_result": rule, "llm_result": llm}


# ── Static frontend ───────────────────────────────────────────────────────────
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
def index():
    page = STATIC_DIR / "index.html"
    if page.exists():
        return FileResponse(str(page))
    return JSONResponse({"app": "Attestia Claims", "error": "static/index.html missing"})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8600)
