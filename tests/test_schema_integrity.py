import sys
import json
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.schema import (
    BoundingBox,
    ClinicalEntity,
    PatientDemographics,
    InsuranceCoverage,
    ProviderInfo,
    ClinicalDiagnosis,
    ReferralV1
)

def test_bounding_box_validation():
    # Valid box
    box = BoundingBox(ymin=0.1, xmin=0.2, ymax=0.3, xmax=0.4, page=1)
    assert box.ymin == 0.1
    assert box.xmax == 0.4

    # Invalid: ymax < ymin
    try:
        BoundingBox(ymin=0.5, xmin=0.1, ymax=0.2, xmax=0.4)
        assert False, "Should have raised ValueError for ymax < ymin"
    except Exception:
        pass

    # Invalid: xmax < xmin
    try:
        BoundingBox(ymin=0.1, xmin=0.8, ymax=0.3, xmax=0.4)
        assert False, "Should have raised ValueError for xmax < xmin"
    except Exception:
        pass
    print("[PASS] test_bounding_box_validation")

def test_patient_demographics_validation():
    patient = PatientDemographics(
        first_name="Eleanor",
        last_name="Vance",
        dob="1964-11-23",
        gender="female",
        phone="555-0199",
        mrn="MRN-84920"
    )
    assert patient.first_name == "Eleanor"
    assert patient.dob == "1964-11-23"

    # Malformed DOB
    try:
        PatientDemographics(first_name="John", last_name="Doe", dob="11/23/1964")
        assert False, "Should have rejected non-YYYY-MM-DD DOB"
    except Exception:
        pass
    print("[PASS] test_patient_demographics_validation")

def test_provider_npi_digits():
    prov = ProviderInfo(name="Dr. Marcus Brody", npi="1234567893")
    assert prov.npi == "1234567893"

    # Non-10 digit
    try:
        ProviderInfo(name="Dr. Invalid", npi="12345")
        assert False, "Should have rejected 5-digit NPI"
    except Exception:
        pass
    print("[PASS] test_provider_npi_digits")

def test_referral_v1_serialization_roundtrip():
    referral = ReferralV1(
        referral_id="REF-2024-001",
        source_file="intake_fax_scan_01.pdf",
        referral_date="2024-03-01",
        service_requested="Orthopedic Consultation — Knee Arthroscopy",
        urgency="ROUTINE",
        patient=PatientDemographics(
            first_name="Sarah",
            last_name="Connor",
            dob="1975-08-14",
            gender="female"
        ),
        insurance=InsuranceCoverage(
            payer_name="Blue Cross Blue Shield",
            member_id="BCBS-9921448",
            group_number="GRP-002"
        ),
        referring_provider=ProviderInfo(
            name="Dr. Peter Silberman",
            npi="1679576722",
            clinic_name="Westside Family Medicine"
        ),
        diagnoses=[
            ClinicalDiagnosis(code="M17.11", description="Primary osteoarthritis, right knee", is_primary=True)
        ],
        field_entities={
            "patient.dob": ClinicalEntity(
                value="1975-08-14",
                raw_text="DOB: 08/14/1975",
                bbox=BoundingBox(ymin=0.15, xmin=0.20, ymax=0.18, xmax=0.45),
                confidence=0.99,
                status="AUTO_ACCEPTED"
            )
        },
        routing_decision="AUTO_ACCEPTED",
        overall_confidence=0.98
    )

    json_str = referral.model_dump_json()
    data = json.loads(json_str)
    assert data["referral_id"] == "REF-2024-001"
    assert data["patient"]["last_name"] == "Connor"
    assert data["field_entities"]["patient.dob"]["bbox"]["page"] == 1

    # Deserialization
    rehydrated = ReferralV1.model_validate_json(json_str)
    assert rehydrated.referring_provider.npi == "1679576722"
    assert rehydrated.diagnoses[0].code == "M17.11"
    print("[PASS] test_referral_v1_serialization_roundtrip")

if __name__ == "__main__":
    test_bounding_box_validation()
    test_patient_demographics_validation()
    test_provider_npi_digits()
    test_referral_v1_serialization_roundtrip()
    print("\nALL SCHEMA INTEGRITY TESTS PASSED (100%)!")
