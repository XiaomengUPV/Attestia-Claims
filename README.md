# Fraud Detection System

Medical insurance claim fraud detection using CPT/ICD-10 code analysis.

## Fraud Types Detected
1. Upcoding
2. Unbundling
3. Code Padding
4. Phantom Billing
5. Diagnosis Mismatch
6. Code Substitution
7. Modifier Abuse (-59)
8. Duplicate Billing
9. Screening Code Abuse

## Pipeline
PDF → OCR → Field Extraction → Rule Checks + LLM Reasoning → Fraud Flag
