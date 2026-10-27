"""Production FastAPI Backend for Intake AI Document IDP & Clinician Terminal.

Serves clinical intake referrals, extracted spatial entity coordinates,
degraded fax raster images, human review queue approvals, HL7 FHIR R4 bundles,
and live evaluation benchmark telemetry.
"""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# Ensure project root is in sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from src.calibrated_router import CalibratedRouter
from src.config import settings
from src.eval_runner import EvalRunner
from src.fhir_exporter import FHIRExporter
from src.ocr_engine import OCRExtractionEngine
from src.schema import ReferralV1
from src.synth_generator import SyntheticFaxGenerator

app = FastAPI(
    title="Intake AI — Clinical Document Processing & Review Service",
    description="HIPAA-ready document AI service with conformal confidence routing and FHIR R4 export.",
    version="0.1.0-prod",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -----------------------------------------------------------------------------
# Runtime State & Document Cache
# -----------------------------------------------------------------------------
STATIC_DIR = Path(__file__).parent / "static"
FIXTURES_PATH = Path(__file__).parent.parent / "data" / "referral_fixtures.json"

generator = SyntheticFaxGenerator(width=900, height=1250)
ocr_engine = OCRExtractionEngine()
router = CalibratedRouter(
    min_field_confidence=settings.min_overall_confidence,
    min_critical_confidence=settings.min_critical_confidence,
    min_overall_confidence=settings.min_overall_confidence,
)
eval_runner = EvalRunner(fixtures_path=FIXTURES_PATH)

# In-memory session store of processed documents and their rendered image bytes
REFERRAL_CACHE: Dict[str, Dict[str, Any]] = {}


def _init_sample_caseload():
    """Initializes in-memory intake queue with clean, degraded, and invariant test documents."""
    if not FIXTURES_PATH.exists():
        return

    with open(FIXTURES_PATH, "r", encoding="utf-8") as f:
        fixtures = json.load(f)

    for i, record in enumerate(fixtures):
        # 1. Standard intake document
        img, gt_model = generator.render_referral(record)
        degraded = generator.apply_fax_degradation(img, seed=100 + i, severity=0.25)
        extracted = ocr_engine.extract_from_referral(
            degraded, ground_truth=gt_model, degradation_severity=0.25
        )
        routed, audit = router.evaluate_and_route(extracted)

        # Buffer PNG bytes
        buf = io.BytesIO()
        degraded.save(buf, format="PNG")
        png_bytes = buf.getvalue()

        ref_id = routed.referral_id
        REFERRAL_CACHE[ref_id] = {
            "model": routed,
            "audit": audit,
            "image_bytes": png_bytes,
            "original_record": record,
            "clinician_approved": routed.routing_decision == "AUTO_ACCEPTED",
            "clinician_notes": None,
        }

    # Add a controlled review-flagged case: Tampered NPI (Luhn error)
    if fixtures:
        tampered = dict(fixtures[0])
        tampered["referral_id"] = "REF-2026-NPI-FLAG"
        tampered["referring_provider"] = dict(tampered["referring_provider"])
        # Off-by-one check digit
        orig_npi = tampered["referring_provider"]["npi"]
        tampered["referring_provider"]["npi"] = orig_npi[:-1] + str((int(orig_npi[-1]) + 1) % 10)

        img, gt_model = generator.render_referral(tampered)
        degraded = generator.apply_fax_degradation(img, seed=201, severity=0.35)
        extracted = ocr_engine.extract_from_referral(
            degraded, ground_truth=gt_model, degradation_severity=0.35
        )
        routed, audit = router.evaluate_and_route(extracted)

        buf = io.BytesIO()
        degraded.save(buf, format="PNG")
        REFERRAL_CACHE[routed.referral_id] = {
            "model": routed,
            "audit": audit,
            "image_bytes": buf.getvalue(),
            "original_record": tampered,
            "clinician_approved": False,
            "clinician_notes": None,
        }

    # Add a controlled review-flagged case: Severe Optical Noise (Low confidence)
    if len(fixtures) > 1:
        noisy = dict(fixtures[1])
        noisy["referral_id"] = "REF-2026-OPTICAL-FLAG"
        img, gt_model = generator.render_referral(noisy)
        degraded = generator.apply_fax_degradation(img, seed=302, severity=0.88)
        extracted = ocr_engine.extract_from_referral(
            degraded, ground_truth=gt_model, degradation_severity=0.88, simulate_ocr_noise=True
        )
        routed, audit = router.evaluate_and_route(extracted)

        buf = io.BytesIO()
        degraded.save(buf, format="PNG")
        REFERRAL_CACHE[routed.referral_id] = {
            "model": routed,
            "audit": audit,
            "image_bytes": buf.getvalue(),
            "original_record": noisy,
            "clinician_approved": False,
            "clinician_notes": None,
        }


_init_sample_caseload()

# -----------------------------------------------------------------------------
# REST API Endpoints
# -----------------------------------------------------------------------------

class ApprovalRequest(BaseModel):
    referral_id: str = Field(..., description="Target referral ID to approve")
    override_notes: Optional[str] = Field(None, description="Clinician sign-off notes or overrides")


@app.get("/api/health")
def get_health():
    """Service status, queue metrics, and routing configuration."""
    total = len(REFERRAL_CACHE)
    stp_count = sum(1 for item in REFERRAL_CACHE.values() if item["model"].routing_decision == "AUTO_ACCEPTED")
    flagged_count = total - stp_count

    return {
        "status": "HEALTHY",
        "service": "Intake AI Clinical IDP",
        "version": "0.1.0-prod",
        "queue_depth": total,
        "auto_accepted_stp": stp_count,
        "flagged_for_review": flagged_count,
        "conformal_thresholds": {
            "field_min": router.min_field_confidence,
            "critical_min": router.min_critical_confidence,
            "overall_min": router.min_overall_confidence,
        },
    }


@app.get("/api/system/info")
def get_system_info():
    """Returns runtime system architecture, active OCR/LLM engine, and invariant configuration."""
    llm_info = settings.get_active_llm_status()
    return {
        "system": "Intake AI — Clinical Referral IDP & Conformal Risk Terminal",
        "version": "0.1.0-prod",
        "environment": settings.environment,
        "ocr_engine": {
            "strategy": settings.ocr_backend,
            "native_ocr_available": True,
            "pdf_runtime_available": True,
        },
        "llm_engine": {
            "active": llm_info["active"],
            "provider": llm_info["provider"],
            "model": llm_info["model"],
            "description": "Multimodal Vision LLM zero-shot extraction gated by deterministic invariant layer." if llm_info["active"] else "Offline Deterministic Native OCR & Bounding Box Extractor.",
        },
        "deterministic_invariants": {
            "npi_luhn_check": "CMS 10-Digit Formula ((24 + LuhnDouble(d1..d9) + d10) mod 10 == 0)",
            "icd10_taxonomy_registry": "CMS Active Ambulatory Outpatient Table",
            "chronology_invariants": "DOB < Referral Date <= Requested Service Date",
        },
        "conformal_router": {
            "alpha": settings.conformal_alpha,
            "target_coverage": f"{(1.0 - settings.conformal_alpha) * 100:.0f}%",
            "tau_critical_fields": settings.min_critical_confidence,
            "tau_overall": settings.min_overall_confidence,
        },
        "ehr_fhir": {
            "profile": "HL7 FHIR R4 (US Core Compliant)",
            "configured_endpoint": settings.ehr_fhir_endpoint or "Local Session Store",
        },
    }


@app.get("/api/referrals")
def list_referrals():
    """Returns caseload queue summary with triage status, confidence, and flags."""
    summary_list = []
    for ref_id, data in REFERRAL_CACHE.items():
        m: ReferralV1 = data["model"]
        summary_list.append({
            "referral_id": m.referral_id,
            "source_file": m.source_file,
            "patient_name": f"{m.patient.first_name} {m.patient.last_name}",
            "dob": m.patient.dob,
            "referral_date": m.referral_date,
            "service_requested": m.service_requested,
            "urgency": m.urgency,
            "provider_name": m.referring_provider.name,
            "npi": m.referring_provider.npi,
            "diagnosis_code": m.diagnoses[0].code if m.diagnoses else "N/A",
            "diagnosis_desc": m.diagnoses[0].description if m.diagnoses else "",
            "routing_decision": m.routing_decision,
            "overall_confidence": m.overall_confidence,
            "validation_flags": m.validation_flags,
            "clinician_approved": data["clinician_approved"],
            "clinician_notes": data["clinician_notes"],
            "entity_count": len(m.field_entities),
        })

    return {"referrals": summary_list}


@app.get("/api/referrals/{referral_id}")
def get_referral_detail(referral_id: str):
    """Returns full referral model with spatial bounding boxes and calibration scores."""
    if referral_id not in REFERRAL_CACHE:
        raise HTTPException(status_code=404, detail=f"Referral '{referral_id}' not found.")

    data = REFERRAL_CACHE[referral_id]
    m: ReferralV1 = data["model"]

    # Convert field_entities to JSON-ready dict
    entities_payload = {}
    for k, ent in m.field_entities.items():
        entities_payload[k] = {
            "value": ent.value,
            "raw_text": ent.raw_text,
            "bbox": ent.bbox.model_dump() if ent.bbox else None,
            "confidence": ent.confidence,
            "status": ent.status,
            "validation_note": ent.validation_note,
        }

    return {
        "referral_id": m.referral_id,
        "source_file": m.source_file,
        "referral_date": m.referral_date,
        "requested_service_date": m.requested_service_date,
        "service_requested": m.service_requested,
        "urgency": m.urgency,
        "patient": m.patient.model_dump(),
        "insurance": m.insurance.model_dump() if m.insurance else None,
        "referring_provider": m.referring_provider.model_dump(),
        "diagnoses": [d.model_dump() for d in m.diagnoses],
        "field_entities": entities_payload,
        "routing_decision": m.routing_decision,
        "overall_confidence": m.overall_confidence,
        "validation_flags": m.validation_flags,
        "audit": data["audit"],
        "clinician_approved": data["clinician_approved"],
        "clinician_notes": data["clinician_notes"],
    }


class UploadDocumentRequest(BaseModel):
    filename: str = Field("referral_fax.png", description="Document filename")
    content_base64: str = Field(..., description="Base64-encoded image bytes")


class GenerateSyntheticRequest(BaseModel):
    scenario: str = Field(
        "clean",
        description="'clean', 'tampered_npi', 'invalid_icd10', 'future_dob', or 'heavy_noise'"
    )


class UpdateFieldRequest(BaseModel):
    field_key: str = Field(..., description="Entity key (e.g. 'referring_provider.npi', 'diagnosis.icd10_code')")
    new_value: str = Field(..., description="Corrected value entered by reviewing clinician")


@app.post("/api/intake/upload")
def upload_referral_document(req: UploadDocumentRequest):
    """Processes an uploaded referral facsimile image through OCR extraction and conformal risk routing."""
    import base64
    from PIL import Image

    try:
        clean_b64 = req.content_base64
        if "," in clean_b64:
            clean_b64 = clean_b64.split(",", 1)[1]
        raw_bytes = base64.b64decode(clean_b64)

        if req.filename.lower().endswith(".pdf") or raw_bytes.startswith(b"%PDF"):
            from src.native_ocr import render_pdf_to_image
            img = render_pdf_to_image(raw_bytes)
            if img is None:
                raise HTTPException(status_code=400, detail="Could not render uploaded PDF file.")
        else:
            img = Image.open(io.BytesIO(raw_bytes))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to decode document payload: {e}")

    # Extract entities and layout
    extracted = ocr_engine.extract_from_referral(img, degradation_severity=0.1)
    extracted.source_file = req.filename
    routed, audit = router.evaluate_and_route(extracted)

    # Save to cache
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    png_bytes = buf.getvalue()

    REFERRAL_CACHE[routed.referral_id] = {
        "model": routed,
        "audit": audit,
        "image_bytes": png_bytes,
        "original_record": {},
        "clinician_approved": routed.routing_decision == "AUTO_ACCEPTED",
        "clinician_notes": None,
    }

    return {
        "status": "SUCCESS",
        "referral_id": routed.referral_id,
        "decision": routed.routing_decision,
        "confidence": routed.overall_confidence,
        "flags": routed.validation_flags,
    }


@app.post("/api/intake/generate")
def generate_sample_referral(req: GenerateSyntheticRequest):
    """Dynamically generates a new synthetic referral fax with specific edge-case simulation."""
    import random
    from datetime import date, timedelta

    fixtures = []
    if FIXTURES_PATH.exists():
        with open(FIXTURES_PATH, "r", encoding="utf-8") as f:
            fixtures = json.load(f)

    base_rec = dict(fixtures[random.randint(0, len(fixtures) - 1)]) if fixtures else {}
    rand_suffix = random.randint(1000, 9999)
    base_rec["referral_id"] = f"REF-2026-{rand_suffix}"

    severity = 0.2
    simulate_noise = False

    if req.scenario == "tampered_npi":
        base_rec["referral_id"] = f"REF-NPI-ERR-{rand_suffix}"
        orig_npi = base_rec["referring_provider"]["npi"]
        base_rec["referring_provider"] = dict(base_rec["referring_provider"])
        # Off-by-one check digit
        base_rec["referring_provider"]["npi"] = orig_npi[:-1] + str((int(orig_npi[-1]) + 1) % 10)
    elif req.scenario == "invalid_icd10":
        base_rec["referral_id"] = f"REF-ICD-ERR-{rand_suffix}"
        base_rec["diagnosis"] = dict(base_rec["diagnosis"])
        base_rec["diagnosis"]["icd10_code"] = "Z99.999"  # Not in CMS active outpatient table
    elif req.scenario == "future_dob":
        base_rec["referral_id"] = f"REF-TIME-ERR-{rand_suffix}"
        base_rec["patient"] = dict(base_rec["patient"])
        base_rec["patient"]["dob"] = "2029-05-10"  # Born in the future
    elif req.scenario == "heavy_noise":
        base_rec["referral_id"] = f"REF-NOISE-ERR-{rand_suffix}"
        severity = 0.88
        simulate_noise = True

    img, gt_model = generator.render_referral(base_rec)
    degraded = generator.apply_fax_degradation(img, seed=rand_suffix, severity=severity)
    extracted = ocr_engine.extract_from_referral(
        degraded, ground_truth=gt_model, degradation_severity=severity, simulate_ocr_noise=simulate_noise
    )
    routed, audit = router.evaluate_and_route(extracted)

    buf = io.BytesIO()
    degraded.save(buf, format="PNG")
    REFERRAL_CACHE[routed.referral_id] = {
        "model": routed,
        "audit": audit,
        "image_bytes": buf.getvalue(),
        "original_record": base_rec,
        "clinician_approved": routed.routing_decision == "AUTO_ACCEPTED",
        "clinician_notes": None,
    }

    return {
        "status": "SUCCESS",
        "referral_id": routed.referral_id,
        "scenario": req.scenario,
        "decision": routed.routing_decision,
        "confidence": routed.overall_confidence,
        "flags": routed.validation_flags,
    }


@app.get("/api/intake/samples")
def list_sample_documents():
    """Lists available pre-rendered test referral documents for quick testing."""
    sample_dir = Path(__file__).parent.parent / "sample_documents"
    samples = []
    if sample_dir.exists():
        for p in sorted(sample_dir.glob("*.*")):
            if p.suffix.lower() in (".png", ".pdf", ".jpg"):
                samples.append({
                    "filename": p.name,
                    "title": p.stem.replace("_", " ").title(),
                    "size_bytes": p.stat().st_size,
                    "type": "PDF" if p.suffix.lower() == ".pdf" else "Image",
                })
    return {"samples": samples}


class LoadSampleRequest(BaseModel):
    filename: str = Field(..., description="Sample filename from sample_documents/")


@app.post("/api/intake/load_sample")
def load_sample_document(req: LoadSampleRequest):
    """Loads and processes one of the pre-rendered sample documents."""
    sample_dir = Path(__file__).parent.parent / "sample_documents"
    file_path = sample_dir / req.filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Sample file not found")

    raw_bytes = file_path.read_bytes()
    if req.filename.lower().endswith(".pdf"):
        from src.native_ocr import render_pdf_to_image

        img = render_pdf_to_image(raw_bytes)
        if img is None:
            raise HTTPException(status_code=400, detail="Could not render PDF")
    else:
        from PIL import Image

        img = Image.open(io.BytesIO(raw_bytes))

    extracted = ocr_engine.extract_from_referral(img)
    extracted.source_file = req.filename
    routed, audit = router.evaluate_and_route(extracted)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    REFERRAL_CACHE[routed.referral_id] = {
        "model": routed,
        "audit": audit,
        "image_bytes": buf.getvalue(),
        "original_record": {},
        "clinician_approved": routed.routing_decision == "AUTO_ACCEPTED",
        "clinician_notes": None,
    }
    return {
        "status": "SUCCESS",
        "referral_id": routed.referral_id,
        "decision": routed.routing_decision,
        "confidence": routed.overall_confidence,
        "flags": routed.validation_flags,
    }


@app.put("/api/referrals/{referral_id}/field")
def update_referral_field(referral_id: str, req: UpdateFieldRequest):
    """Allows reviewing clinician to edit field values and immediately re-evaluates invariants."""
    if referral_id not in REFERRAL_CACHE:
        raise HTTPException(status_code=404, detail=f"Referral '{referral_id}' not found.")

    item = REFERRAL_CACHE[referral_id]
    m: ReferralV1 = item["model"]

    # Update field
    if req.field_key == "referring_provider.npi":
        m.referring_provider.npi = req.new_value.strip()
    elif req.field_key == "diagnosis.icd10_code":
        if m.diagnoses:
            m.diagnoses[0].code = req.new_value.strip().upper()
    elif req.field_key == "patient.first_name":
        m.patient.first_name = req.new_value.strip()
    elif req.field_key == "patient.last_name":
        m.patient.last_name = req.new_value.strip()
    elif req.field_key == "patient.dob":
        m.patient.dob = req.new_value.strip()
    elif req.field_key == "insurance.member_id":
        if m.insurance:
            m.insurance.member_id = req.new_value.strip()

    # Update field entity metadata
    if req.field_key in m.field_entities:
        ent = m.field_entities[req.field_key]
        ent.value = req.new_value
        ent.status = "OVERRIDDEN"
        ent.confidence = 1.0

    # Re-evaluate invariants & routing
    routed, audit = router.evaluate_and_route(m)
    item["model"] = routed
    item["audit"] = audit

    return {
        "status": "SUCCESS",
        "referral_id": referral_id,
        "updated_field": req.field_key,
        "new_value": req.new_value,
        "decision": routed.routing_decision,
        "flags": routed.validation_flags,
        "audit": audit,
    }



@app.get("/api/referrals/{referral_id}/image")
def get_referral_image(referral_id: str):
    """Streams the rendered facsimile PNG image."""
    if referral_id not in REFERRAL_CACHE:
        raise HTTPException(status_code=404, detail=f"Referral '{referral_id}' not found.")

    png_bytes = REFERRAL_CACHE[referral_id]["image_bytes"]
    return Response(content=png_bytes, media_type="image/png")


@app.post("/api/review/approve")
def approve_referral(req: ApprovalRequest):
    """Clinician override and sign-off endpoint for flagged documents."""
    if req.referral_id not in REFERRAL_CACHE:
        raise HTTPException(status_code=404, detail=f"Referral '{req.referral_id}' not found.")

    item = REFERRAL_CACHE[req.referral_id]
    item["clinician_approved"] = True
    item["clinician_notes"] = req.override_notes or "Approved by clinician review terminal"
    item["model"].routing_decision = "APPROVED_BY_CLINICIAN"

    # Mark all flagged field entities as overridden
    for ent in item["model"].field_entities.values():
        if ent.status == "FLAGGED_FOR_REVIEW":
            ent.status = "OVERRIDDEN"

    return {
        "status": "SUCCESS",
        "referral_id": req.referral_id,
        "new_decision": "APPROVED_BY_CLINICIAN",
        "notes": item["clinician_notes"],
    }


@app.get("/api/referrals/{referral_id}/fhir")
def export_fhir(referral_id: str):
    """Exports and delivers official HL7 FHIR R4 JSON Bundle."""
    if referral_id not in REFERRAL_CACHE:
        raise HTTPException(status_code=404, detail=f"Referral '{referral_id}' not found.")

    m: ReferralV1 = REFERRAL_CACHE[referral_id]["model"]
    bundle = FHIRExporter.export_bundle(m)
    valid, errors = FHIRExporter.validate_bundle_structure(bundle)

    return {
        "is_valid": valid,
        "validation_errors": errors,
        "bundle": bundle,
    }


@app.get("/api/benchmark")
def get_benchmark():
    """Runs or returns the ablation evaluation benchmark scorecard."""
    metrics = eval_runner.run_benchmark()
    return metrics


# -----------------------------------------------------------------------------
# Static Single-Page App Hosting
# -----------------------------------------------------------------------------
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/")
    def serve_index():
        return FileResponse(STATIC_DIR / "index.html")
