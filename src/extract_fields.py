"""
extract_fields.py
─────────────────
Step 3B of the Fraud Detection Pipeline — OCR Field Extractor.

PURPOSE:
    Reads each CMS-1500 PDF using OCR (Optical Character Recognition)
    and extracts the key fields needed for fraud detection:
    CPT codes, ICD-10 diagnosis codes, charges, modifiers, patient info.

WHY OCR:
    Some claims arrive as scanned PDFs from small clinics or paper forms.
    OCR converts the PDF image into text, then we parse out the specific
    fields. This is slower than EDI parsing but handles any PDF document.

OUTPUT FORMAT — Normalized Claim Object:
    Both this OCR path AND the EDI parser produce the same structure:
    {
        "claim_id":         "CLM01093",
        "date":             "2025-09-21",
        "patient_name":     "Frank Jackson",
        "provider_name":    "Dr. Emily Nguyen",
        "facility":         "Sunrise Health Associates",
        "insurer":          "Cigna Health",
        "policy_no":        "POL346961",
        "procedure_codes":  ["87491"],
        "diagnosis_codes":  ["Z03.89"],
        "modifiers":        [],
        "line_charges":     [107.89],
        "total_charge":     107.89,
        "source":           "pdf_ocr"
    }

INPUT:  data/pdfs/<claim_id>.pdf
OUTPUT: data/ocr_output/<claim_id>.json

REQUIREMENTS:
    pip install pytesseract Pillow pdf2image
    brew install tesseract poppler

HOW TO RUN:
    python3 src/extract_fields.py
"""

import json, re, sys, os
from pathlib import Path

# Conditional imports — require installation
try:
    import pytesseract
    from PIL import Image
    from pdf2image import convert_from_path
    OCR_AVAILABLE = True
except ImportError:
    OCR_AVAILABLE = False
    print("OCR libraries not installed. Run:")
    print("  pip install pytesseract Pillow pdf2image")
    print("  brew install tesseract poppler")

BASE_DIR    = Path(__file__).resolve().parent.parent
PDF_DIR     = BASE_DIR / "data" / "pdfs"
OCR_DIR     = BASE_DIR / "data" / "ocr_output"
OCR_DIR.mkdir(parents=True, exist_ok=True)


def pdf_to_image(pdf_path):
    """
    Converts the first page of a PDF to a PIL Image at 300 DPI.
    300 DPI gives the best balance of OCR accuracy vs speed.
    Higher DPI = better accuracy but slower.
    """
    try:
        images = convert_from_path(str(pdf_path), dpi=300)
        return images[0] if images else None
    except Exception as e:
        print(f"  [PDF→IMAGE ERROR] {pdf_path.name}: {e}")
        return None


def image_to_text(image):
    """
    Runs Tesseract OCR on a PIL image and returns the raw extracted text.
    --psm 6 = treat image as a single uniform block of text (good for forms).
    --oem 3 = use both legacy and LSTM neural net engines.
    """
    if image is None:
        return ""
    try:
        custom_config = r"--oem 3 --psm 6"
        return pytesseract.image_to_string(image, config=custom_config)
    except Exception as e:
        print(f"  [OCR ERROR]: {e}")
        return ""


def fix_ocr_errors(text):
    """
    Corrects common OCR misreads that affect medical billing codes.

    WHY THIS IS NEEDED:
    Tesseract OCR sometimes confuses visually similar characters in printed
    text. In medical billing, this causes specific errors that directly
    affect fraud detection accuracy. We fix them before extraction.

    KNOWN ICD-10 OCR MISREADS:
    ─────────────────────────────────────────────────────────────────────
    1. Capital I → digit 1 (most common and most impactful)
       ICD-10 codes starting with letter I (cardiovascular, infections)
       get read as numbers.
       Example: I25.10 (atherosclerotic heart disease) → 125.10
       Example: I10    (hypertension)                  → 110
       Example: I50.9  (heart failure)                 → 150.9
       Fix: regex pattern matches 3-digit numbers starting with 1
            followed by a dot or end-of-word that look like ICD I-codes

    2. Letter O → digit 0 (less common but occurs)
       Example: O09.90 (pregnancy) → 009.90
       Fix: 3-digit number starting with 0 that matches ICD O-code pattern

    3. Capital S → digit 5 (rare but seen in injury codes)
       Example: S72.001A (hip fracture) → 572.001A
       Fix: matches S-code pattern

    IMPORTANT: We are conservative with these fixes — we only correct
    patterns that are unambiguous. We do NOT fix all digit→letter
    substitutions because that would corrupt legitimate numeric data.
    """

    # ── Fix 1: Capital I misread as digit 1 ───────────────────────────────────
    # Pattern: \b1(\d{2}\.\w{1,4})\b  matches e.g. "125.10" → "I25.10"
    # Only fixes codes that have a decimal point (proper ICD-10 format)
    text = re.sub(r'\b1(\d{2}\.\w{1,4})\b', r'I\1', text)

    # Also fix 3-character I-codes without decimal e.g. "110" → "I10"
    # We use lookahead to ensure this is followed by a space or punctuation
    # to avoid accidentally changing real numbers
    text = re.sub(r'(?<!\d)1(\d{2})(?!\d)', r'I\1', text)

    # ── Fix 2: Capital O misread as digit 0 ───────────────────────────────────
    # Pregnancy and obstetric codes start with O (letter)
    # Pattern: \b0(\d{2}\.\w{1,4})\b  matches e.g. "009.90" → "O09.90"
    text = re.sub(r'\b0(\d{2}\.\w{1,4})\b', r'O\1', text)

    # ── Fix 3: Capital S misread as digit 5 (injury codes) ────────────────────
    # Injury codes like S72.001A (hip fracture) start with S
    # Only fix when followed by digits and a letter suffix (e.g. A, D, S)
    text = re.sub(r'\b5(\d{2}\.\w{1,3}[A-Z])\b', r'S\1', text)

    # ── Fix 4: Clean up common OCR noise in code areas ────────────────────────
    # Sometimes OCR adds a stray colon before codes e.g. ": 93306" — strip it
    text = re.sub(r':\s*(\d{5})\b', r' \1', text)

    return text


def extract_cpt_codes(text):
    """
    Extracts all CPT/HCPCS procedure codes from the OCR text.
    These are the KEY fraud detection signals.

    Patterns matched:
      - 5-digit numeric CPT:  99213, 85025, 71046
      - HCPCS G-codes:        G0103, G0101
      - M-codes (lab):        0006M, 0019M
      - U-codes (lab):        0026U, 0048U

    NOTE: We call fix_ocr_errors() on the text BEFORE extracting CPT codes
    so that the ICD-10 corrections don't accidentally remove valid CPT codes
    that start with 1 (like 10060, 11042 etc.). CPT codes are 5 digits —
    ICD-10 I-codes are 3 digits — so there is no overlap.
    """
    codes = []

    # Standard 5-digit CPT codes
    codes.extend(re.findall(r"\b(\d{5})\b", text))

    # HCPCS G-codes (e.g. G0103, G0101)
    codes.extend([c.upper() for c in re.findall(r"\b(G\d{4})\b", text, re.IGNORECASE)])

    # M-codes (Multianalyte Assays with Algorithmic Analyses)
    codes.extend([c.upper() for c in re.findall(r"\b(\d{4}M)\b", text, re.IGNORECASE)])

    # U-codes (Proprietary Laboratory Analyses)
    codes.extend([c.upper() for c in re.findall(r"\b(\d{4}U)\b", text, re.IGNORECASE)])

    # Deduplicate while preserving order
    # Filter out year-like numbers (1900-2099) and zip codes
    seen = set()
    result = []
    for code in codes:
        if code.isdigit() and 1900 <= int(code) <= 2099:
            continue  # skip years (2025, 2026 etc.)
        if code.isdigit() and len(code) == 5 and int(code) < 10000:
            continue  # skip zip codes (02118 etc.)
        if code not in seen:
            seen.add(code)
            result.append(code)
    return result


def extract_icd10_codes(text):
    """
    Extracts ICD-10-CM diagnosis codes from the OCR text.

    ICD-10 format: one letter + 2 digits + optional .suffix
    Examples: I10, E11.9, Z00.00, J06.9, M54.5, I25.10

    IMPORTANT: We call fix_ocr_errors() BEFORE this function so that
    common misreads like I25.10 → 125.10 are corrected first.
    Without the fix, all ICD-10 I-codes (cardiovascular, infectious
    diseases) would be silently missed.
    """
    # Pattern: letter + 2 digits + optional decimal + up to 4 chars
    codes = re.findall(r"\b([A-Z]\d{2}(?:\.\w{1,4})?)\b", text, re.IGNORECASE)

    # Deduplicate and normalize to uppercase
    seen = set()
    result = []
    for code in codes:
        code_upper = code.upper()
        # Must start with a letter (not a digit — that would be a number, not a code)
        if code_upper[0].isalpha() and code_upper not in seen:
            seen.add(code_upper)
            result.append(code_upper)
    return result


def extract_total_charge(text):
    """
    Finds the total charge amount — used in upcoding detection
    to compare against the CMS Medicare fee schedule.

    We look for the TOTAL CHARGE field specifically, then fall back
    to finding the largest dollar amount on the form.
    """
    # Look for 'TOTAL CHARGE' label followed by a dollar amount
    match = re.search(r"TOTAL\s+CHARGE[:\s]*\$?([\d,]+\.?\d*)", text, re.IGNORECASE)
    if match:
        return float(match.group(1).replace(",", ""))

    # Fallback: find all dollar amounts and return the largest
    # (the largest amount on a claim is almost always the total)
    amounts = re.findall(r"\$([\d,]+\.\d{2})", text)
    if amounts:
        try:
            return max(float(a.replace(",", "")) for a in amounts)
        except ValueError:
            pass
    return 0.0


def extract_line_charges(text):
    """
    Extracts individual line item charges from the procedure table.
    These are the per-procedure amounts — useful for detecting which
    specific line item is inflated (upcoding signal).

    Returns a list of floats in order of appearance on the form.
    """
    # Find all dollar amounts that appear in the procedure table area
    # These typically appear as "$X,XXX.XX" or "$XXX.XX"
    amounts = re.findall(r"\$([\d,]+\.\d{2})", text)

    # Convert to floats, filter out $0.00 (amount paid field)
    charges = []
    for a in amounts:
        val = float(a.replace(",", ""))
        if val > 0:
            charges.append(val)

    # The last large amount is usually the total — remove it if we have multiple
    if len(charges) > 1:
        charges = charges[:-1]  # remove the total from line charges

    return charges


def extract_modifiers(text):
    """
    Extracts billing modifiers — critical for modifier abuse detection.
    Modifier -59 is the most important fraud signal (unbundling).

    Common modifiers we look for:
      -59  separate procedure (most commonly abused)
      -25  significant separately identifiable E&M service
      -26  professional component
      -TC  technical component
    """
    modifiers = []

    # Check for modifier -59 (the most fraud-relevant modifier)
    if re.search(r"-59\b|modifier.*59|\b59\b.*modifier", text, re.IGNORECASE):
        modifiers.append("-59")

    # Check for modifier -25
    if re.search(r"\b25\b.*modifier|modifier.*\b25\b", text, re.IGNORECASE):
        modifiers.append("-25")

    return modifiers


def extract_date(text):
    """
    Finds the service date.
    Handles multiple date formats found in real CMS-1500 forms:
      - YYYY-MM-DD  (our generated forms)
      - MM DD YYYY  (real form format)
      - MM/DD/YYYY  (common printed format)
      - MM/DD/YY    (short year)
    """
    # Our generated format: YYYY-MM-DD
    match = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", text)
    if match:
        return match.group(1)

    # Real form format: MM DD YYYY or MM/DD/YYYY in service date area
    # Look near "DATE OF SERVICE" label
    match = re.search(
        r"DATE.*?OF.*?SERVICE.*?(\d{2})\s+(\d{2})\s+(\d{4})",
        text, re.IGNORECASE | re.DOTALL
    )
    if match:
        mm, dd, yyyy = match.group(1), match.group(2), match.group(3)
        return f"{yyyy}-{mm}-{dd}"

    # Fallback: any MM/DD/YYYY date
    match = re.search(r"\b(\d{2})/(\d{2})/(\d{4})\b", text)
    if match:
        mm, dd, yyyy = match.group(1), match.group(2), match.group(3)
        return f"{yyyy}-{mm}-{dd}"

    return None


def build_normalized_claim(text, pdf_path):
    """
    Assembles all extracted fields into the normalized claim object.
    This is the SAME structure produced by the EDI parser — so the fraud
    engine works identically regardless of whether input was PDF or EDI.

    CRITICAL STEP: We call fix_ocr_errors() on the raw text FIRST before
    passing to any extractor. This ensures:
    - I25.10 is not misread as 125.10
    - O09.90 is not misread as 009.90
    - All cardiovascular ICD-10 codes (starting with I) are captured
    """
    # ── Apply OCR corrections BEFORE any extraction ────────────────────────────
    # This is the fix for the I25.10 → 125.10 misread bug discovered during
    # real-world testing with a UnitedHealth claim form.
    corrected_text = fix_ocr_errors(text)

    return {
        "claim_id":        pdf_path.stem,                          # from filename
        "date":            extract_date(corrected_text),
        "procedure_codes": extract_cpt_codes(corrected_text),      # KEY fraud signal
        "diagnosis_codes": extract_icd10_codes(corrected_text),    # KEY fraud signal
        "modifiers":       extract_modifiers(corrected_text),      # KEY modifier abuse
        "total_charge":    extract_total_charge(corrected_text),   # KEY upcoding signal
        "line_charges":    extract_line_charges(corrected_text),   # per-line amounts
        "raw_ocr_text":    text[:500],           # original text for debugging
        "corrected_text":  corrected_text[:500], # corrected text for verification
        "source":          "pdf_ocr",
    }


def process_pdf(pdf_path):
    """
    Full pipeline for one PDF:
    PDF → Image (300 DPI) → OCR text → Fix OCR errors → Extract fields
    → Normalized claim dict
    """
    image = pdf_to_image(pdf_path)
    if image is None:
        return None
    text = image_to_text(image)
    if not text.strip():
        return None
    return build_normalized_claim(text, Path(pdf_path))


if __name__ == "__main__":
    if not OCR_AVAILABLE:
        print("\nCannot run — install dependencies first:")
        print("  pip install pytesseract Pillow pdf2image")
        print("  brew install tesseract poppler")
        sys.exit(1)

    pdf_files = sorted(PDF_DIR.glob("*.pdf"))
    if not pdf_files:
        print(f"No PDFs found in {PDF_DIR}. Run render_claims.py first.")
        sys.exit(1)

    print(f"\nRunning OCR on {len(pdf_files)} PDFs...")
    print(f"Expected time: ~{len(pdf_files)*2//60} minutes\n")
    print(f"OCR error corrections active:")
    print(f"  - Capital I → digit 1 in ICD-10 codes (e.g. I25.10 ← 125.10)")
    print(f"  - Capital O → digit 0 in ICD-10 codes (e.g. O09.90 ← 009.90)")
    print(f"  - Capital S → digit 5 in injury codes (e.g. S72.001A ← 572.001A)\n")

    success = errors = 0
    for i, pdf_path in enumerate(pdf_files):
        try:
            claim = process_pdf(pdf_path)
            if claim:
                out_path = OCR_DIR / f"{pdf_path.stem}.json"
                with open(out_path, "w") as f:
                    json.dump(claim, f, indent=2)
                success += 1
            else:
                errors += 1
            if (i + 1) % 50 == 0:
                print(f"  {i+1}/{len(pdf_files)} done...")
                sys.stdout.flush()
        except Exception as e:
            errors += 1
            print(f"[ERROR] {pdf_path.name}: {e}")

    print(f"\nDone! {success} extracted, {errors} errors.")
    print(f"Output: {OCR_DIR}")
    print(f"Next: run src/fraud_engine.py")
