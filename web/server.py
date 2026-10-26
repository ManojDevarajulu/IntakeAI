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
from src.eval_runner import EvalRunner
from src.fhir_exporter import FHIRExporter
from src.ocr_engine import OCRExtractionEngine
from src.schema import ReferralV1
from src.synth_generator import SyntheticFaxGenerator

app = FastAPI(
    title="Intake AI — Clinical Document Processing & Review Service",
    description="HIPAA-ready document AI service with conformal confidence routing and FHIR R4 export.",
    version="0.1.0",
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
    min_field_confidence=0.85,
    min_critical_confidence=0.88,
    min_overall_confidence=0.85,
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
        "version": "0.1.0",
        "queue_depth": total,
        "auto_accepted_stp": stp_count,
        "flagged_for_review": flagged_count,
        "conformal_thresholds": {
            "field_min": router.min_field_confidence,
            "critical_min": router.min_critical_confidence,
            "overall_min": router.min_overall_confidence,
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
