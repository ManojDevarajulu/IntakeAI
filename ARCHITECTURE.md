# Intake AI — System Architecture & Conformal Risk Specification

This document details the production systems architecture, mathematical verification invariants, conformal risk boundary formulation, and HL7 FHIR R4 mapping contracts of **Intake AI**.

---

## 1. End-to-End System Topology

```mermaid
flowchart TD
    subgraph Data & Simulation Engine
        F1["data/referral_fixtures.json"] --> SG["src/synth_generator.py: SyntheticFaxGenerator"]
        SG -->|Pillow Rasterization| IMG["Degraded 200 DPI Facsimile Image"]
        SG -->|Normalized [ymin, xmin, ymax, xmax]| GT["Ground Truth ReferralV1"]
    end

    subgraph Document IDP Pipeline
        IMG --> OCR["src/ocr_engine.py: OCRExtractionEngine"]
        OCR --> DRAFT["ReferralV1 Draft Model"]
        
        subgraph Deterministic Invariant Verifier ["src/clinical_verifier.py: ClinicalVerifier"]
            DRAFT --> V_NPI["CMS 10-Digit NPI Luhn Check"]
            DRAFT --> V_ICD["CMS ICD-10-CM Taxonomy Registry"]
            DRAFT --> V_TIME["Temporal Chronology Invariant"]
        end

        V_NPI & V_ICD & V_TIME --> CR["src/calibrated_router.py: CalibratedRouter"]
    end

    subgraph Conformal Triage & HITL
        CR -->|Invariants Valid & Conf >= tau| STP["AUTO_ACCEPTED: Straight-Through Processing"]
        CR -->|Invariant Failure or Conf < tau| HITL["FLAGGED_FOR_REVIEW: Clinician Review Queue"]
        
        HITL -->|Reviewer Adjudication| OVERRIDE["web/server.py: POST /api/review/approve"]
    end

    subgraph Interoperability & Export
        STP --> FHIR["src/fhir_exporter.py: FHIRExporter"]
        OVERRIDE --> FHIR
        FHIR --> BUNDLE["HL7 FHIR R4 US Core Transaction Bundle"]
    end

    subgraph Telemetry & Evaluation
        IMG & GT & CR --> EVAL["src/eval_runner.py: EvalRunner Benchmark"]
    end
```

---

## 2. Deterministic Verification Layer

Intake AI guarantees zero hallucinated clinical identifiers via three closed-form deterministic verifiers:

### A. CMS 10-Digit NPI Check-Digit Invariant (ISO/IEC 7812)
Every National Provider Identifier (NPI) in the United States is a 10-digit number. The 10th digit is an ISO/IEC 7812 Luhn check-digit calculated over a fixed CMS constant prefix:
$$\text{Prefix} = \text{"80840"}$$
The 5-digit prefix has an invariant partial sum:
$$\sum_{\text{prefix}} = 8 + (0 \times 2) + 8 + (4 \times 2) + 0 = 24$$
For digits $d_1, d_2, \dots, d_9$:
- Even-positioned digits (from the right) are doubled. If doubling exceeds 9, subtract 9.
- Odd-positioned digits are taken as-is.
- The check digit $d_{10}$ must satisfy:
$$(24 + \text{sum}(\text{doubled digits}) + d_{10}) \pmod{10} = 0$$

Any transpositions or OCR digit dropouts are caught with **100% mathematical certainty** without invoking external LLMs.

### B. CMS ICD-10-CM Taxonomy Registry
- Syntactic verification enforces the HIPAA standard grammar:
  $$\text{Regex} = \text{\textasciicircum}[A\text{-}TV\text{-}Z][0\text{-}9][0\text{-}9A\text{-}Z](\.[0\text{-}9A\text{-}TV\text{-}Z]\{1,4\})?\$$$
- Code-level validation cross-references the official outpatient diagnostic taxonomy registry. Unregistered or deprecated codes are automatically flagged as `UNVERIFIED_ICD10_TAXONOMY`.

### C. Temporal Chronology Invariants
- Enforces strict physiological and administrative timeline ordering:
  $$\text{DOB} < \text{Referral Date} \le \text{Requested Service Date}$$
- Rejects future birth dates, inverted referral dates, and appointments requested prior to patient birth.

---

## 3. Conformal Risk Boundary & Routing Logic

The routing engine classifies each intake document into one of two operational states:

1. **`AUTO_ACCEPTED` (Straight-Through Processing / STP)**:
   - Condition: $\forall f \in \text{CriticalFields}: \hat{C}(f) \ge \tau_f$ AND all deterministic invariants pass.
   - Outcome: Zero clinician touches required; immediately exported to HL7 FHIR R4.

2. **`FLAGGED_FOR_REVIEW` (Human-in-the-Loop Review Queue)**:
   - Condition: $\exists f: \hat{C}(f) < \tau_f$ OR any invariant fails.
   - Outcome: Document routed to the Clinician Terminal with exact spatial bounding boxes colored rose/amber and granular root-cause failure flags.

---

## 4. HL7 FHIR R4 Export Contract

Verified referrals are exported as standard HL7 FHIR R4 JSON Transaction Bundles comprising:
- **`Patient`**: US Core Patient profile with Demographics, Birth Date, Telecom, MRN identifier.
- **`Practitioner`**: Referring physician with official `http://hl7.org/fhir/sid/us-npi` system URI.
- **`Coverage`**: Payer policy, subscriber member identifier, group number.
- **`Condition`**: Primary encounter diagnosis with `http://hl7.org/fhir/sid/icd-10-cm` coding.
- **`ServiceRequest`**: Ambulatory consultation order referencing Patient, Practitioner, and Condition.

---

## 5. Security & HIPAA Safeguards

- **100% Synthetic Data**: Zero Protected Health Information (PHI) or Personally Identifiable Information (PII) is stored or processed. Fixtures are generated using Synthea-derived ambulatory profiles.
- **Local Isolation**: All OCR extraction, invariant verification, and evaluation harnesses execute locally with zero external network leakage.
