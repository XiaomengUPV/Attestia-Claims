"""
render_clean_claims.py
──────────────────────
Renders CMS-1500 PDFs WITHOUT the fraud verdict banner at the bottom.

PURPOSE:
    These "clean" PDFs are used for the demo — they look exactly like
    a real claim form as submitted by a doctor's office. No fraud label,
    no "why flagged" box, no green/red banner. The fraud detection system
    then analyzes them and tells us if they are fraudulent.

    The original render_claims.py produces PDFs with the verdict pre-printed
    for training/evaluation purposes. This script produces realistic PDFs
    for demo purposes.

INPUT:  data/raw_claims/claims.json
OUTPUT: data/pdfs_clean/<claim_id>.pdf

HOW TO RUN:
    python3 src/render_clean_claims.py
"""

import json, sys
from pathlib import Path
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.units import inch

BASE_DIR    = Path(__file__).resolve().parent.parent
CLAIMS_JSON = BASE_DIR / "data" / "raw_claims" / "claims.json"
PDF_DIR     = BASE_DIR / "data" / "pdfs_clean"   # separate folder — no verdict
PDF_DIR.mkdir(parents=True, exist_ok=True)

W, H = letter
NAVY      = colors.HexColor("#1A3A5C")
LGRAY     = colors.HexColor("#F4F4F4")
MGRAY     = colors.HexColor("#CCCCCC")
DGRAY     = colors.HexColor("#444444")
M_LEFT    = 0.35 * inch
M_RIGHT   = W - 0.35 * inch
CW        = M_RIGHT - M_LEFT
LSIZE     = 5.5
VSIZE     = 8.0
ROW_H     = 0.40 * inch


def labeled_box(c, x, y, w, h, label, value,
                vs=VSIZE, bold=False, bg=None, vc=colors.black, truncate=True):
    """Draws a field box with label at top and value at bottom — no overlap."""
    c.setStrokeColor(MGRAY); c.setLineWidth(0.4)
    if bg:
        c.setFillColor(bg); c.rect(x, y-h, w, h, fill=1, stroke=1)
    else:
        c.rect(x, y-h, w, h, fill=0, stroke=1)
    c.setFillColor(DGRAY); c.setFont("Helvetica", LSIZE)
    c.drawString(x+3, y-LSIZE-3, label)
    if value:
        c.setFillColor(vc)
        c.setFont("Helvetica-Bold" if bold else "Helvetica", vs)
        max_chars = max(1, int((w-8) / (vs*0.58)))
        c.drawString(x+4, y-h+8, str(value)[:max_chars] if truncate else str(value))


def hline(c, x1, x2, y, w=0.5, col=MGRAY):
    c.setStrokeColor(col); c.setLineWidth(w); c.line(x1, y, x2, y)


def render_clean_claim(claim, out_path):
    """
    Renders a CMS-1500 claim form WITHOUT any fraud verdict.
    Looks exactly like a real submitted claim form.
    The fraud detection system will analyze this to determine if it's fraud.
    """
    c = canvas.Canvas(str(out_path), pagesize=letter)
    y = H - 0.2 * inch

    # HEADER — same as original but no claim ID hint about fraud
    c.setFillColor(NAVY); c.rect(M_LEFT, y-0.50*inch, CW, 0.50*inch, fill=1, stroke=0)
    c.setFillColor(colors.white); c.setFont("Helvetica-Bold", 12)
    c.drawString(M_LEFT+8, y-18, "HEALTH INSURANCE CLAIM FORM")
    c.setFont("Helvetica", 7); c.setFillColor(colors.HexColor("#AED6F1"))
    c.drawString(M_LEFT+8, y-30, "APPROVED BY NATIONAL UNIFORM CLAIM COMMITTEE (NUCC)  |  CMS-1500 (02-12)")
    c.setFillColor(colors.white); c.setFont("Helvetica-Bold", 8)
    c.drawRightString(M_RIGHT-6, y-18, f"CLAIM ID: {claim['claim_id']}")
    c.setFont("Helvetica", 7); c.setFillColor(colors.HexColor("#AED6F1"))
    c.drawRightString(M_RIGHT-6, y-30, f"DATE: {claim['date']}")
    y -= 0.56*inch

    # ROW 1: Insurance type + Insured ID
    w1 = CW*0.55
    labeled_box(c, M_LEFT,    y, w1,    ROW_H, "1. INSURANCE TYPE", "☑ OTHER / PRIVATE INSURANCE", bg=LGRAY)
    labeled_box(c, M_LEFT+w1, y, CW-w1, ROW_H, "1a. INSURED'S I.D. NUMBER", claim["patient"]["policy_no"], bold=True)
    y -= ROW_H

    # ROW 2: Patient name | DOB | Sex | Insured name
    a,b,cc = CW*0.38, CW*0.17, CW*0.09; d=CW-a-b-cc
    labeled_box(c, M_LEFT,       y, a,  ROW_H, "2. PATIENT NAME (Last, First, MI)", claim["patient"]["name"], bold=True)
    labeled_box(c, M_LEFT+a,     y, b,  ROW_H, "3. DATE OF BIRTH", claim["patient"]["dob"])
    labeled_box(c, M_LEFT+a+b,   y, cc, ROW_H, "SEX", claim["patient"]["sex"], bold=True)
    labeled_box(c, M_LEFT+a+b+cc,y, d,  ROW_H, "4. INSURED'S NAME", claim["patient"]["name"])
    y -= ROW_H

    # ROW 3: Addresses
    w1 = CW*0.55
    labeled_box(c, M_LEFT,    y, w1,    ROW_H, "5. PATIENT ADDRESS", claim["patient"]["address"][:52])
    labeled_box(c, M_LEFT+w1, y, CW-w1, ROW_H, "7. INSURED ADDRESS", claim["patient"]["address"][:38])
    y -= ROW_H

    # ROW 4: Insurance plan | Group | Policy
    p1,p2,p3 = CW*0.50, CW*0.28, CW*0.22
    labeled_box(c, M_LEFT,       y, p1, ROW_H, "11c. INSURANCE PLAN OR PROGRAM NAME", claim["patient"]["insurer"], bold=True, bg=LGRAY)
    labeled_box(c, M_LEFT+p1,    y, p2, ROW_H, "11. POLICY GROUP NUMBER", claim["patient"]["group_no"], bg=LGRAY)
    labeled_box(c, M_LEFT+p1+p2, y, p3, ROW_H, "POLICY NO.", claim["patient"]["policy_no"], bg=LGRAY)
    y -= ROW_H + 0.10*inch

    # PROVIDER ROW
    hline(c, M_LEFT, M_RIGHT, y+0.04*inch, w=1.2, col=NAVY)
    pr1,pr2,pr3 = CW*0.46, CW*0.35, CW*0.19
    labeled_box(c, M_LEFT,         y, pr1, ROW_H, "17. TREATING PHYSICIAN", claim["provider"]["name"], bold=True)
    labeled_box(c, M_LEFT+pr1,     y, pr2, ROW_H, "32. SERVICE FACILITY", claim["provider"]["facility"])
    labeled_box(c, M_LEFT+pr1+pr2, y, pr3, ROW_H, "NPI", claim["provider"]["npi"][:12])
    y -= ROW_H + 0.10*inch

    # DIAGNOSIS SECTION
    hline(c, M_LEFT, M_RIGHT, y+0.04*inch, w=1.2, col=NAVY)
    dh = 0.58*inch   # taller box — 3 lines: label, codes, descriptions
    c.setFillColor(LGRAY); c.setStrokeColor(MGRAY); c.setLineWidth(0.4)
    c.rect(M_LEFT, y-dh, CW, dh, fill=1, stroke=1)
    # Label pinned to top
    c.setFillColor(DGRAY); c.setFont("Helvetica", LSIZE)
    c.drawString(M_LEFT+4, y-LSIZE-3, "21. DIAGNOSIS OR NATURE OF ILLNESS OR INJURY (ICD-10-CM)")
    diag_codes = claim.get("diagnosis_codes", [])
    diag_descs = claim.get("diagnosis_descs", [])
    # Codes on second line — well below label
    c.setFillColor(NAVY); c.setFont("Helvetica-Bold", 9)
    c.drawString(M_LEFT+4, y-LSIZE-18, "  |  ".join(diag_codes))
    # Descriptions on third line — well below codes
    c.setFillColor(DGRAY); c.setFont("Helvetica", 7.5)
    c.drawString(M_LEFT+4, y-LSIZE-30, "  |  ".join([d[:60] for d in diag_descs]))
    y -= dh + 0.10*inch

    # PROCEDURES TABLE HEADER
    COLS = [("DATE",0.11),("POS",0.05),("CPT/HCPCS",0.14),("DESCRIPTION",0.24),
            ("MODIFIER",0.09),("DIAG PTR",0.08),("$ CHARGES",0.13),("UNITS",0.07),("NPI",0.09)]
    col_pts = [(n, f*CW) for n,f in COLS]
    hdr_h = 0.22*inch
    c.setFillColor(NAVY); c.rect(M_LEFT, y-hdr_h, CW, hdr_h, fill=1, stroke=0)
    cx = M_LEFT
    for name, cw in col_pts:
        c.setFillColor(colors.white); c.setFont("Helvetica-Bold", 5.5)
        c.drawString(cx+3, y-hdr_h+7, name)
        if cx+cw < M_RIGHT-1:
            c.setStrokeColor(colors.HexColor("#4A6A8A")); c.setLineWidth(0.3)
            c.line(cx+cw, y, cx+cw, y-hdr_h)
        cx += cw
    y -= hdr_h

    # PROCEDURE LINES
    proc_codes   = claim.get("procedure_codes", [])
    proc_descs   = claim.get("procedure_descs", [])
    line_charges = claim.get("line_charges", [])
    modifiers    = claim.get("modifiers", [])
    n_lines = min(len(proc_codes), 6)
    lh = 0.30*inch
    for li in range(6):
        bg = LGRAY if li%2==0 else colors.white
        c.setFillColor(bg); c.setStrokeColor(MGRAY); c.setLineWidth(0.3)
        c.rect(M_LEFT, y-lh, CW, lh, fill=1, stroke=1)
        if li < n_lines:
            row_vals = [
                claim["date"], "11",
                proc_codes[li] if li<len(proc_codes) else "",
                (proc_descs[li][:36] if li<len(proc_descs) else ""),
                (modifiers[li] if li<len(modifiers) else ""),
                "A",
                (f"${line_charges[li]:,.2f}" if li<len(line_charges) else ""),
                "1", claim["provider"]["npi"][:10],
            ]
            cx = M_LEFT
            for vi,(val,(col_name,cw)) in enumerate(zip(row_vals,col_pts)):
                fc = NAVY if vi==2 else (colors.HexColor("#C0392B") if vi==6 else colors.black)
                fb = vi in [2,6]
                c.setFillColor(fc); c.setFont("Helvetica-Bold" if fb else "Helvetica", 7.5)
                c.drawString(cx+3, y-lh+10, str(val))
                if cx+cw < M_RIGHT-1:
                    c.setStrokeColor(MGRAY); c.setLineWidth(0.3)
                    c.line(cx+cw, y, cx+cw, y-lh)
                cx += cw
        y -= lh

    y -= 0.08*inch
    hline(c, M_LEFT, M_RIGHT, y, w=1.2, col=NAVY)
    y -= 0.08*inch

    # TOTALS ROW
    tot_h = 0.42*inch
    c.setFillColor(LGRAY); c.setStrokeColor(MGRAY); c.setLineWidth(0.4)
    c.rect(M_LEFT, y-tot_h, CW, tot_h, fill=1, stroke=1)
    total = claim.get("total_charge", 0)
    c.setFillColor(DGRAY); c.setFont("Helvetica", LSIZE)
    c.drawString(M_LEFT+4, y-LSIZE-3, "25. FEDERAL TAX I.D. NUMBER")
    c.setFillColor(colors.black); c.setFont("Helvetica", 8)
    c.drawString(M_LEFT+4, y-tot_h+9, claim["provider"]["tax_id"])
    tc_x = M_LEFT+CW*0.48
    c.setFillColor(DGRAY); c.setFont("Helvetica", LSIZE)
    c.drawString(tc_x, y-LSIZE-3, "28. TOTAL CHARGE")
    c.setFillColor(NAVY); c.setFont("Helvetica-Bold", 13)
    c.drawString(tc_x, y-tot_h+9, f"${total:,.2f}")
    ap_x = M_LEFT+CW*0.74
    c.setFillColor(DGRAY); c.setFont("Helvetica", LSIZE)
    c.drawString(ap_x, y-LSIZE-3, "29. AMOUNT PAID")
    c.setFillColor(colors.black); c.setFont("Helvetica", 8)
    c.drawString(ap_x, y-tot_h+9, "$0.00")
    y -= tot_h

    # SIGNATURE ROW
    sig_h = 0.38*inch; s1 = CW*0.60
    c.setFillColor(colors.white); c.setStrokeColor(MGRAY); c.setLineWidth(0.4)
    c.rect(M_LEFT,    y-sig_h, s1,    sig_h, fill=1, stroke=1)
    c.rect(M_LEFT+s1, y-sig_h, CW-s1, sig_h, fill=1, stroke=1)
    c.setFillColor(DGRAY); c.setFont("Helvetica", LSIZE)
    c.drawString(M_LEFT+4, y-LSIZE-3, "31. SIGNATURE OF PHYSICIAN OR SUPPLIER")
    c.setFillColor(colors.black); c.setFont("Helvetica", 7.5)
    c.drawString(M_LEFT+4, y-sig_h+9, f"Signed: {claim['provider']['name']}    Date: {claim['date']}")
    c.setFillColor(DGRAY); c.setFont("Helvetica", LSIZE)
    c.drawString(M_LEFT+s1+4, y-LSIZE-3, "33. BILLING PROVIDER INFO & PH #")
    c.setFillColor(colors.black); c.setFont("Helvetica", 7.5)
    c.drawString(M_LEFT+s1+4, y-sig_h+9, claim["provider"]["facility"])
    y -= sig_h + 0.10*inch

    # FOOTER — standard CMS footer, no fraud indicator
    fy = 0.18*inch
    hline(c, M_LEFT, M_RIGHT, fy+0.14*inch, w=0.5, col=NAVY)
    c.setFillColor(DGRAY); c.setFont("Helvetica", 5.5)
    c.drawString(M_LEFT, fy,
        "NUCC Instruction Manual: www.nucc.org  |  CMS-1500 (02-12)  |  APPROVED OMB-0938-1197")
    c.save()


if __name__ == "__main__":
    with open(CLAIMS_JSON) as f:
        claims = json.load(f)

    print(f"\nRendering {len(claims)} clean CMS-1500 PDFs (no fraud verdict)...")
    print(f"Output: {PDF_DIR}\n")

    errors = 0
    for i, claim in enumerate(claims):
        try:
            render_clean_claim(claim, PDF_DIR / f"{claim['claim_id']}.pdf")
            if (i+1) % 100 == 0:
                print(f"  {i+1}/{len(claims)} done...")
                sys.stdout.flush()
        except Exception as e:
            errors += 1
            print(f"[ERROR] {claim['claim_id']}: {e}")

    print(f"\n✅  Done! {len(claims)-errors} clean PDFs generated in {PDF_DIR}")
    print(f"These PDFs have no fraud verdict — ready for demo use.")
