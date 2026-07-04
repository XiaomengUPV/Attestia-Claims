# Anti-Fraud-System
### Medical Insurance Claim Fraud Detection Using AI & Code Analysis
---

## What This Project Does

This system takes a single medical insurance claim — exactly as it arrives at an insurance company — and automatically determines:

- ✅ **Is it fraudulent?** (Yes / No)
- 🏷️ **What type of fraud?** (one of 9 specific fraud patterns)
- 📝 **Why was it flagged?** (plain-English explanation an investigator can act on)

The system works on a **single document with no reference or history required** — matching how real insurance reviewers work.

---

## The Problem We're Solving

Medical billing fraud costs the US between **$68–$230 billion per year** (FBI estimate) — roughly 3–10 cents of every healthcare dollar. Existing systems fail because:

- **Manual review** is slow, inconsistent, and can't scale to millions of claims
- **Historical pattern analysis** takes months to detect fraud and misses first-time fraudsters
- **Neither approach** can evaluate a single claim in isolation, the moment it arrives

**Our system fills this gap** — evaluating every claim independently the moment it arrives, using only the information in that one document.

---

## The 9 Fraud Types We Detect

| # | Fraud Type | What It Means | Detection Method | Risk |
|---|---|---|---|---|
| 1 | **Upcoding** | Bill for a more expensive service than what was done | LLM | 🔴 High |
| 2 | **Unbundling** | Split one procedure into multiple codes to charge more | Rule-based | 🔴 High |
| 3 | **Code Padding** | Add unrelated high-value codes to inflate the total | LLM | 🔴 High |
| 4 | **Phantom Billing** | Charge for a procedure that was never performed | LLM | 🔴 High |
| 5 | **Diagnosis Mismatch** | Pair a procedure with a wrong/unrelated diagnosis | LLM | 🟡 Medium |
| 6 | **Code Substitution** | Swap a non-covered code for a covered-sounding one | LLM | 🟡 Medium |
| 7 | **Modifier Abuse (-59)** | Misuse modifier -59 to bypass bundling rules | Rule-based | 🟡 Medium |
| 8 | **Duplicate Billing** | Submit the same code twice for the same visit | Rule-based | 🟢 Low |
| 9 | **Screening Code Abuse** | Bill a screening test without the required diagnosis | Rule-based | 🟢 Low |

---

## How It Works — The Pipeline

The system accepts claims in **two formats** (matching real-world workflows):

```
┌─────────────────────────────────────────────────────────────┐
│                      INPUT LAYER                            │
│                                                             │
│   PDF Claim (paper/scan)        EDI 837 File (electronic)   │
│   ~5% of real-world claims      ~95% of real-world claims   │
│         ↓                               ↓                   │
│    OCR Engine                      EDI Parser               │
│   (pytesseract)                  (custom X12 parser)        │
│         ↓                               ↓                   │
│   ─────────────────────────────────────────────────────     │
│              NORMALIZED CLAIM OBJECT                        │
│   {cpt_codes, icd10_codes, modifiers, charges,              │
│    patient, provider, date}                                 │
│   ─────────────────────────────────────────────────────     │
│                         ↓                                   │
│   ┌─────────────────────────────────────────────────────┐   │
│   │           FRAUD DETECTION ENGINE                    │   │
│   │                                                     │   │
│   │  Rule-Based Checks (Python)                        │   │
│   │  → Duplicate billing, Unbundling,                  │   │
│   │    Modifier abuse, Screening code abuse            │   │
│   │                                                     │   │
│   │  LLM Reasoning (Claude API)                        │   │
│   │  → Upcoding, Code padding, Phantom billing,        │   │
│   │    Diagnosis mismatch, Code substitution           │   │
│   └─────────────────────────────────────────────────────┘   │
│                         ↓                                   │
│          FRAUD VERDICT + TYPE + EXPLANATION                 │
└─────────────────────────────────────────────────────────────┘
```

---

## Data Sources Used

| Source | What It Is | How We Use It |
|---|---|---|
| **2026 DHS Code List Addendum** | Official CMS list of 1,500+ valid CPT/HCPCS codes | Source of truth for all procedure codes in our dataset |
| **ICD-10-CM Tabular** | Official diagnosis code list | Source of truth for all diagnosis codes |
| **CMS 2026 Physician Fee Schedule** | Official Medicare payment rates per CPT code | Price plausibility checks for upcoding detection |
| **NCCI PTP Edit Tables** | 675,000+ code pairs that cannot be billed together | Unbundling and modifier abuse detection |
| **CMS-1500 Form Standard** | Universal physician claim form (NUCC) | PDF template for all synthetic claims |
| **EDI 837P Standard** | X12 electronic claim transaction format | Electronic input format (95% of real claims) |

---

## Dataset

We generated **1,300 synthetic CMS-1500 claims** — all using real CPT and ICD-10 codes:

| Class | Count | Description |
|---|---|---|
| Legitimate | 400 | Internally consistent — correct CPT/ICD pairings, realistic prices |
| Upcoding | 120 | More expensive code billed than service warranted |
| Diagnosis Mismatch | 120 | CPT code has no valid relationship to the diagnosis |
| Unbundling | 100 | Component codes billed separately instead of one comprehensive code |
| Code Padding | 100 | Unrelated high-value codes added to a real claim |
| Phantom Billing | 100 | Clinically impossible procedure given the diagnosis |
| Code Substitution | 100 | Non-covered procedure swapped for a covered code |
| Modifier Abuse (-59) | 100 | Modifier -59 used to bypass NCCI bundling rules |
| Duplicate Billing | 80 | Same CPT code billed twice for the same visit |
| Screening Code Abuse | 80 | Screening test billed without required diagnosis code |
| **Total** | **1,300** | |

Each claim is stored in 3 formats:
- `.json` — structured ground truth with fraud label and explanation
- `.pdf` — rendered CMS-1500 form (input to OCR pipeline)
- `.edi` — EDI 837P transaction (input to EDI parser pipeline)

---

## Project Structure

```
Anti-Fraud-System/
├── src/
│   ├── generate_claims.py    # Step 1: Generate 1,300 synthetic claims as JSON
│   ├── render_claims.py      # Step 2: Render each claim as a CMS-1500 PDF
│   ├── generate_edi.py       # Step 3A: Convert each claim to EDI 837P format
│   ├── extract_fields.py     # Step 3B: OCR pipeline — PDF → structured fields
│   ├── parse_edi.py          # Step 3C: EDI parser — .edi → structured fields
│   ├── rule_checks.py        # Step 4A: Rule-based fraud detection (4 types)
│   ├── llm_checker.py        # Step 4B: Claude API reasoning (5 types)
│   ├── fraud_engine.py       # Step 4C: Merge rule + LLM results
│   ├── evaluate.py           # Step 5: Precision, recall, F1 per fraud type
│   └── api.py                # Step 6: Attestia Claims — FastAPI backend
├── static/
│   └── index.html            # Attestia Claims — single-page review console
├── data/
│   ├── raw_claims/           # JSON claims + CSV summary
│   ├── pdfs/                 # CMS-1500 PDF files (1,300)
│   ├── edi/                  # EDI 837P files (1,300)
│   ├── edi_parsed/           # Parsed EDI → JSON (1,300)
│   ├── ocr_output/           # OCR extracted fields → JSON
│   ├── splits/               # Train/val/test split
│   ├── cms_fee_schedule.xlsx # CMS 2026 Medicare fee schedule
│   └── ncci_edits.xlsx       # NCCI procedure-to-procedure edit tables
├── Progress/                 # Session reports and documentation
├── models/                   # Trained model artifacts
├── reports/                  # Evaluation results and charts
├── .gitignore
└── README.md
```

---

## Build Progress

| Step | Script | Status | Description |
|---|---|---|---|
| 1 | `generate_claims.py` | ✅ Complete | 1,300 synthetic claims generated |
| 2 | `render_claims.py` | ✅ Complete | 1,300 CMS-1500 PDFs rendered |
| 3A | `generate_edi.py` | ✅ Complete | 1,300 EDI 837P files generated |
| 3B | `extract_fields.py` | ✅ Complete | OCR pipeline built |
| 3C | `parse_edi.py` | ✅ Complete | EDI parser built |
| 4A | `rule_checks.py` | ✅ Complete | Rule-based fraud checks (4 types) |
| 4B | `llm_checker.py` | ✅ Complete | Claude API reasoning layer (5 types) |
| 4C | `fraud_engine.py` | ✅ Complete | Merges rule + LLM results into final verdicts |
| 5 | `evaluate.py` | ✅ Complete | Precision, recall, F1 — see `reports/` |
| 6 | Attestia Claims (`api.py` + `static/`) | ✅ Complete | FastAPI + SPA review console: browse claims, upload EDI → verdict |

---

## Why CMS-1500?

The CMS-1500 is the universal standard claim form used by physicians, specialists, clinics, and outpatient facilities across the entire United States — mandated by CMS and accepted by virtually every insurance payer. It covers office visits, lab tests, imaging, cardiac procedures, specialist consultations, and more.

The system architecture is designed to be **form-agnostic at the fraud detection layer** — adding UB-04 (hospital/inpatient) support later requires only a new field extractor, not a rebuild of the fraud engine.

---

## Why Both PDF and EDI?

| | PDF Path | EDI Path |
|---|---|---|
| Real-world usage | ~5% of claims | ~95% of claims |
| Extraction method | OCR (pytesseract) | Direct text parsing |
| Accuracy | ~95% | 100% |
| Speed | ~2–3 sec per claim | <0.1 sec per claim |
| Best for | Small clinics, audit review, demo | Production systems |

Both paths produce an identical **normalized claim object** that feeds into the same fraud detection engine.

---

## How to Run

```bash
# 1. Clone and set up
git clone https://github.com/XiaomengUPV/Anti-Fraud-System.git
cd Anti-Fraud-System
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
brew install tesseract poppler   # Mac only

# 2. Generate dataset
python3 src/generate_claims.py   # Step 1: 1,300 JSON claims
python3 src/render_claims.py     # Step 2: 1,300 PDFs
python3 src/generate_edi.py      # Step 3A: 1,300 EDI files
python3 src/parse_edi.py         # Step 3C: Parse EDI → JSON

# 3. Run fraud detection + evaluation
export ANTHROPIC_API_KEY="your-key-here"
python3 src/rule_checks.py       # Step 4A: rule-based checks
python3 src/llm_checker.py       # Step 4B: LLM reasoning layer
python3 src/fraud_engine.py      # Step 4C: merge into final verdicts
python3 src/evaluate.py          # Step 5: precision / recall / F1 report

# 4. Launch the Attestia Claims review console
python src/api.py
# -> open http://localhost:8600
```

---

## Target Metrics

| Metric | Target |
|---|---|
| Binary fraud F1 (fraud vs. legitimate) | ≥ 0.85 |
| Per-fraud-type F1 (average across 9 types) | ≥ 0.75 |
| False positive rate (legitimate flagged as fraud) | < 10% |

---

## Results

Evaluated on all 1,300 claims with the rule engine + Claude Sonnet. The LLM confidence
threshold (`ACCEPTED_LLM_CONFIDENCE` in `fraud_engine.py`) is a configurable operating
point — the precision/recall trade-off is a business decision about investigation cost
versus missed-fraud cost, so both modes are reported:

| Metric | Precision mode (default) | Recall mode | Target |
|---|---|---|---|
| Binary F1 | **0.921** | 0.941 | ≥ 0.85 ✅ |
| Precision | 0.980 | 0.937 | — |
| Recall | 0.869 | 0.944 | — |
| Per-type avg F1 | **0.820** | 0.849 | ≥ 0.75 ✅ |
| False positive rate | **4.0%** | 14.3% | < 10% ✅ (precision mode) |

Per-type F1 (precision mode): Duplicate Billing 1.00 · Modifier Abuse 1.00 ·
Code Padding 0.95 · Unbundling 0.89 · Diagnosis Mismatch 0.80 · Code Substitution 0.78 ·
Phantom Billing 0.78 · Screening Abuse 0.75 · Upcoding 0.44 (recall-mode: 0.79 — upcoding
judgments are inherently medium-confidence, so this type benefits most from recall mode).

Full breakdown in `reports/evaluation_report.txt`.

### Key engineering findings

1. **NCCI edits have a structural blind spot.** NCCI PTP pairs are (comprehensive,
   component) — if the comprehensive panel code is absent from the claim, component-split
   unbundling is invisible to table lookup. We added panel-composition detection, taking
   unbundling recall from 0.17 to 1.00.
2. **Some fraud is informationally undetectable from a single claim.** Code substitution
   claims that reuse the covered code's normal price are byte-identical to legitimate
   claims. Realistic substitution retains an economic trace — the true service's charge —
   which our charge/code consistency check detects (per-line charge vs. Medicare rate).
3. **Prompt shortcuts overfit.** Dataset-specific "always flag X" prompt rules produced
   brittle behavior across model versions (precision collapsed to 0.70 in one run).
   Replacing them with general clinical and CMS coding guidance restored precision to 0.98.

---

## Team & Acknowledgments

Developed and maintained by **Hazel Sun** and team — Cornell University, 2026.
Based on an original capstone codebase by S. Poman; this repository extends it with detection improvements, evaluation fixes, and the interactive demo.


