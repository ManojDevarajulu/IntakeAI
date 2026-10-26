"""Comprehensive Test Suite for Phase 3: Extraction, Conformal Router, and FHIR Exporter."""

import json
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.calibrated_router import CalibratedRouter
from src.clinical_verifier import ClinicalVerifier
from src.eval_runner import EvalRunner
from src.fhir_exporter import FHIRExporter
from src.ocr_engine import OCRExtractionEngine
from src.schema import (
    BoundingBox,
    ClinicalDiagnosis,
    ClinicalEntity,
    InsuranceCoverage,
    PatientDemographics,
    ProviderInfo,
    ReferralV1,
)
from src.synth_generator import SyntheticFaxGenerator


def _build_test_referral(
    npi: str = "1234567893",
    icd10: str = "I10",
    dob: str = "1980-05-15",
    confidence: float = 0.95,
) -> ReferralV1:
    return ReferralV1(
        referral_id="REF-TEST-P3",
        source_file="test_sample.png",
        referral_date="2026-03-01",
        requested_service_date="2026-04-01",
        service_requested="Cardiology Consultation",
        urgency="ROUTINE",
        patient=PatientDemographics(
            first_name="Alice",
            last_name="Smith",
            dob=dob,
            gender="female",
            phone="555-0100",
            mrn="MRN-10023",
        ),
        insurance=InsuranceCoverage(
            payer_name="Aetna",
            member_id="AET-8839201",
            group_number="GRP-001",
        ),
        referring_provider=ProviderInfo(
            name="Dr. Gregory House",
            npi=npi,
            clinic_name="Princeton-Plainsboro",
            phone="555-0199",
            fax="555-0198",
        ),
        diagnoses=[ClinicalDiagnosis(code=icd10, description="Essential hypertension", is_primary=True)],
        field_entities={
            "referral_id": ClinicalEntity(value="REF-TEST-P3", raw_text="REF-TEST-P3", bbox=BoundingBox(ymin=0.1, xmin=0.1, ymax=0.15, xmax=0.3), confidence=confidence),
            "patient.first_name": ClinicalEntity(value="Alice", raw_text="Alice", bbox=BoundingBox(ymin=0.2, xmin=0.1, ymax=0.25, xmax=0.3), confidence=confidence),
            "patient.last_name": ClinicalEntity(value="Smith", raw_text="Smith", bbox=BoundingBox(ymin=0.2, xmin=0.3, ymax=0.25, xmax=0.5), confidence=confidence),
            "patient.dob": ClinicalEntity(value=dob, raw_text=dob, bbox=BoundingBox(ymin=0.2, xmin=0.5, ymax=0.25, xmax=0.7), confidence=confidence),
            "referring_provider.npi": ClinicalEntity(value=npi, raw_text=npi, bbox=BoundingBox(ymin=0.4, xmin=0.1, ymax=0.45, xmax=0.3), confidence=confidence),
            "diagnosis.icd10_code": ClinicalEntity(value=icd10, raw_text=icd10, bbox=BoundingBox(ymin=0.5, xmin=0.1, ymax=0.55, xmax=0.3), confidence=confidence),
        },
        routing_decision="PENDING",
        overall_confidence=confidence,
    )


def test_ocr_extraction_engine():
    generator = SyntheticFaxGenerator(width=600, height=800)
    with open("data/referral_fixtures.json", "r", encoding="utf-8") as f:
        fixtures = json.load(f)

    img, gt_model = generator.render_referral(fixtures[0])
    engine = OCRExtractionEngine()

    # Mild degradation extraction
    extracted = engine.extract_from_referral(img, ground_truth=gt_model, degradation_severity=0.2)
    assert extracted.referral_id == gt_model.referral_id
    assert extracted.patient.first_name == gt_model.patient.first_name
    assert extracted.overall_confidence > 0.85
    assert len(extracted.field_entities) >= 6

    # Severe degradation should lower confidence
    extracted_noisy = engine.extract_from_referral(
        img, ground_truth=gt_model, degradation_severity=0.85, simulate_ocr_noise=True
    )
    assert extracted_noisy.overall_confidence < extracted.overall_confidence

    print("[PASS] test_ocr_extraction_engine")


def test_conformal_router_auto_acceptance():
    router = CalibratedRouter()
    ref = _build_test_referral(npi="1234567893", icd10="I10", confidence=0.95)

    routed, audit = router.evaluate_and_route(ref)
    assert routed.routing_decision == "AUTO_ACCEPTED"
    assert audit["stp_eligible"] is True
    assert len(routed.validation_flags) == 0
    assert routed.field_entities["referring_provider.npi"].status == "AUTO_ACCEPTED"

    print("[PASS] test_conformal_router_auto_acceptance")


def test_conformal_router_npi_rejection():
    router = CalibratedRouter()
    # 1234567894 has an invalid Luhn check digit
    ref = _build_test_referral(npi="1234567894", icd10="I10", confidence=0.95)

    routed, audit = router.evaluate_and_route(ref)
    assert routed.routing_decision == "FLAGGED_FOR_REVIEW"
    assert audit["stp_eligible"] is False
    assert any("INVALID_NPI" in f for f in routed.validation_flags)
    assert routed.field_entities["referring_provider.npi"].status == "FLAGGED_FOR_REVIEW"

    print("[PASS] test_conformal_router_npi_rejection")


def test_conformal_router_icd10_rejection():
    router = CalibratedRouter()
    # Z99.999 is outside active verified CMS taxonomy table
    ref = _build_test_referral(npi="1234567893", icd10="Z99.999", confidence=0.95)

    routed, audit = router.evaluate_and_route(ref)
    assert routed.routing_decision == "FLAGGED_FOR_REVIEW"
    assert any("UNVERIFIED_ICD10_TAXONOMY" in f or "INVALID_ICD10" in f for f in routed.validation_flags)
    assert routed.field_entities["diagnosis.icd10_code"].status == "FLAGGED_FOR_REVIEW"

    print("[PASS] test_conformal_router_icd10_rejection")


def test_conformal_router_chronology_rejection():
    router = CalibratedRouter()
    # DOB after referral date
    ref = _build_test_referral(npi="1234567893", icd10="I10", dob="2028-01-01", confidence=0.95)

    routed, audit = router.evaluate_and_route(ref)
    assert routed.routing_decision == "FLAGGED_FOR_REVIEW"
    assert any("CHRONOLOGY_MISMATCH" in f for f in routed.validation_flags)

    print("[PASS] test_conformal_router_chronology_rejection")


def test_conformal_router_low_confidence_flagging():
    router = CalibratedRouter(min_field_confidence=0.85)
    # Low confidence (0.70 < 0.85 threshold)
    ref = _build_test_referral(npi="1234567893", icd10="I10", confidence=0.70)

    routed, audit = router.evaluate_and_route(ref)
    assert routed.routing_decision == "FLAGGED_FOR_REVIEW"
    assert any("LOW_CONFIDENCE" in f for f in routed.validation_flags)

    print("[PASS] test_conformal_router_low_confidence_flagging")


def test_fhir_r4_bundle_export():
    ref = _build_test_referral(npi="1234567893", icd10="I10")
    bundle = FHIRExporter.export_bundle(ref)

    assert bundle["resourceType"] == "Bundle"
    assert bundle["type"] == "transaction"
    assert bundle["total"] == 5

    res_types = [e["resource"]["resourceType"] for e in bundle["entry"]]
    assert "Patient" in res_types
    assert "Practitioner" in res_types
    assert "Coverage" in res_types
    assert "Condition" in res_types
    assert "ServiceRequest" in res_types

    # Find Practitioner and verify NPI identifier system
    prac = next(e["resource"] for e in bundle["entry"] if e["resource"]["resourceType"] == "Practitioner")
    assert prac["identifier"][0]["system"] == "http://hl7.org/fhir/sid/us-npi"
    assert prac["identifier"][0]["value"] == "1234567893"

    # Find Condition and verify ICD-10 coding
    cond = next(e["resource"] for e in bundle["entry"] if e["resource"]["resourceType"] == "Condition")
    assert cond["code"]["coding"][0]["code"] == "I10"

    # Validate structure
    valid, errors = FHIRExporter.validate_bundle_structure(bundle)
    assert valid, f"FHIR validation failed: {errors}"

    print("[PASS] test_fhir_r4_bundle_export")


def test_eval_runner_integration():
    runner = EvalRunner()
    metrics = runner.run_benchmark()

    assert metrics["total_documents_evaluated"] == 20
    assert metrics["stp_rate_clean"] >= 75.0
    assert metrics["safety_catch_npi_luhn"] == 100.0
    assert metrics["safety_catch_icd10"] == 100.0
    assert metrics["safety_catch_chronology"] == 100.0
    assert metrics["overall_safety_sensitivity"] == 100.0
    assert metrics["fhir_export_valid"] is True
    assert metrics["p50_latency_ms"] < 500.0

    print("[PASS] test_eval_runner_integration")


if __name__ == "__main__":
    test_ocr_extraction_engine()
    test_conformal_router_auto_acceptance()
    test_conformal_router_npi_rejection()
    test_conformal_router_icd10_rejection()
    test_conformal_router_chronology_rejection()
    test_conformal_router_low_confidence_flagging()
    test_fhir_r4_bundle_export()
    test_eval_runner_integration()
    print("\nALL PHASE 3 PIPELINE TESTS PASSED (100%)!")
