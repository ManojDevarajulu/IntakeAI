"""Tests for Synthetic Fax Generator & Degradation Pipeline."""

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.clinical_verifier import ClinicalVerifier
from src.synth_generator import SyntheticFaxGenerator


def test_render_referral_integrity():
    generator = SyntheticFaxGenerator(width=1200, height=1600)

    sample_record = {
        "referral_id": "REF-TEST-001",
        "referral_date": "2026-05-01",
        "urgency": "urgent",
        "patient": {
            "first_name": "Sarah",
            "last_name": "Connor",
            "dob": "1984-05-12",
            "gender": "female",
            "phone": "555-019-9921",
            "address": "400 Cyberdyne Blvd, Los Angeles, CA 90001",
        },
        "insurance": {
            "payer_name": "California Shield Care",
            "member_id": "CSC1029384",
            "group_number": "GRP-8812",
        },
        "referring_provider": {
            "provider_name": "Dr. Peter Silberman, MD",
            "npi": "1234567893",
            "clinic_name": "Westside Family Practice",
            "phone": "555-111-2233",
            "fax": "555-111-2234",
        },
        "diagnosis": {
            "icd10_code": "I10",
            "description": "Essential hypertension",
            "clinical_notes": "Patient requires cardiology evaluation.",
        },
        "service_requested": {
            "service_type": "Cardiology Consultation",
            "requested_date": "2026-05-10",
        },
    }

    img, ref_model = generator.render_referral(sample_record)

    # 1. Assert image geometry
    assert img.size == (1200, 1600), f"Expected size (1200, 1600), got {img.size}"
    assert img.mode == "RGB", f"Expected RGB mode, got {img.mode}"

    # 2. Assert Referral Model data
    assert ref_model.referral_id == "REF-TEST-001"
    assert ref_model.patient.first_name == "Sarah"
    assert ref_model.referring_provider.npi == "1234567893"
    assert ref_model.diagnoses[0].code == "I10"

    # 3. Assert Bounding Box normalization
    for name in [
        "referral_id",
        "patient.first_name",
        "patient.dob",
        "insurance.member_id",
        "referring_provider.npi",
        "diagnosis.icd10_code",
    ]:
        entity = ref_model.field_entities.get(name)
        assert entity is not None, f"Entity {name} missing from field_entities"
        box = entity.bbox
        assert box is not None, f"Entity {name} missing bbox"
        assert 0.0 <= box.ymin < box.ymax <= 1.0, f"Invalid y bounds for {name}: {box}"
        assert 0.0 <= box.xmin < box.xmax <= 1.0, f"Invalid x bounds for {name}: {box}"

    print("[PASS] test_render_referral_integrity")


def test_fax_degradation_pipeline():
    generator = SyntheticFaxGenerator(width=600, height=800)

    fixtures_path = Path("data/referral_fixtures.json")
    with open(fixtures_path, "r", encoding="utf-8") as f:
        fixtures = json.load(f)

    img, _ = generator.render_referral(fixtures[0])
    degraded = generator.apply_fax_degradation(img, seed=42, severity=0.7)

    assert degraded.size == img.size, "Degradation altered image dimensions"
    assert degraded.mode == "RGB", "Degraded image must be RGB"

    # Test determinism
    degraded_dup = generator.apply_fax_degradation(img, seed=42, severity=0.7)
    diff = list(degraded.getdata()) == list(degraded_dup.getdata())
    assert diff, "Degradation with same seed must be deterministic"

    print("[PASS] test_fax_degradation_pipeline")


def test_ground_truth_clinical_invariants():
    generator = SyntheticFaxGenerator()
    fixtures_path = Path("data/referral_fixtures.json")

    with open(fixtures_path, "r", encoding="utf-8") as f:
        fixtures = json.load(f)

    for record in fixtures:
        _, ref_model = generator.render_referral(record)

        # 1. Verify CMS NPI Luhn validity
        npi = ref_model.referring_provider.npi
        npi_valid, npi_reason = ClinicalVerifier.validate_npi(npi)
        assert npi_valid, f"Fixture NPI {npi} failed validation: {npi_reason}"

        # 2. Verify CMS ICD-10 validity
        code = ref_model.diagnoses[0].code
        icd_valid, icd_reason, _ = ClinicalVerifier.validate_icd10(code)
        assert icd_valid, f"Fixture ICD-10 {code} failed validation: {icd_reason}"

        # 3. Verify chronological consistency
        chrono_valid, chrono_reason = ClinicalVerifier.validate_chronology(
            dob=ref_model.patient.dob,
            referral_date=ref_model.referral_date,
            service_date=ref_model.requested_service_date,
        )
        assert chrono_valid, f"Fixture chronology failed: {chrono_reason}"

    print("[PASS] test_ground_truth_clinical_invariants")


def test_sample_suite_generation():
    generator = SyntheticFaxGenerator(width=600, height=800)
    fixtures_path = Path("data/referral_fixtures.json")

    tmp_dir = tempfile.mkdtemp(prefix="intake_test_synth_")
    try:
        results = generator.generate_sample_suite(fixtures_path, tmp_dir, degrade=True)
        assert len(results) == 4, f"Expected 4 generated sets, got {len(results)}"

        for img_file, json_file, model in results:
            assert img_file.exists(), f"Image file {img_file} not generated"
            assert json_file.exists(), f"JSON ground truth {json_file} not generated"
            assert os.path.getsize(img_file) > 1000, f"Image file {img_file} too small"

            with open(json_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            assert "referral_id" in data
            assert data["patient"]["first_name"] == model.patient.first_name
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    print("[PASS] test_sample_suite_generation")


if __name__ == "__main__":
    test_render_referral_integrity()
    test_fax_degradation_pipeline()
    test_ground_truth_clinical_invariants()
    test_sample_suite_generation()
    print("\nALL SYNTHETIC GENERATOR TESTS PASSED (100%)!")
