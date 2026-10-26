import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.clinical_verifier import ClinicalVerifier

def test_npi_luhn_validation():
    # Valid real CMS NPIs
    valid_npis = [
        "1234567893",   # Canonical textbook NPI
        "1679576722",   # Valid physician NPI
        "1497758544",   # Valid physician NPI
        "1003000126",   # Valid provider NPI
    ]
    for npi in valid_npis:
        is_valid, msg = ClinicalVerifier.validate_npi(npi)
        assert is_valid, f"Expected {npi} to be valid, got: {msg}"
    print(f"[PASS] test_npi_luhn_validation: verified {len(valid_npis)} valid NPIs.")

    # Invalid NPIs (tampered check digit or malformed)
    invalid_npis = [
        ("1234567894", "Invalid NPI Luhn check digit"),  # Off by 1 check digit
        ("12345", "must contain exactly 10 digits"),       # Too short
        ("123456789012", "must contain exactly 10 digits"),# Too long
        ("abcdefghij", "must contain exactly 10 digits")   # Non-numeric
    ]
    for npi, expected_err in invalid_npis:
        is_valid, msg = ClinicalVerifier.validate_npi(npi)
        assert not is_valid, f"Expected {npi} to be invalid"
        assert expected_err in msg
    print(f"[PASS] test_npi_luhn_validation: rejected {len(invalid_npis)} invalid NPIs.")

def test_icd10_taxonomy_validation():
    # Valid high-frequency CMS codes
    taxonomy_codes = [
        ("E11.9", "Type 2 diabetes mellitus without complications"),
        ("I10", "Essential (primary) hypertension"),
        ("M54.5", "Low back pain"),
        ("J45.909", "Unspecified asthma, uncomplicated"),
        ("C50.919", "Malignant neoplasm of unspecified site of female breast")
    ]
    for code, expected_desc in taxonomy_codes:
        is_valid, msg, desc = ClinicalVerifier.validate_icd10(code)
        assert is_valid, f"Expected {code} to be valid"
        assert desc == expected_desc, f"Expected description '{expected_desc}', got '{desc}'"
    print(f"[PASS] test_icd10_taxonomy_validation: verified {len(taxonomy_codes)} CMS taxonomy codes.")

    # Valid syntax, not in curated dictionary
    is_valid, msg, desc = ClinicalVerifier.validate_icd10("S82.001A")
    assert is_valid
    assert desc is None

    # Invalid formats
    invalid_codes = ["123.45", "INVALID", "E1", "E11.999999"]
    for code in invalid_codes:
        is_valid, msg, desc = ClinicalVerifier.validate_icd10(code)
        assert not is_valid, f"Expected {code} to fail syntax check"
    print(f"[PASS] test_icd10_taxonomy_validation: rejected invalid formats.")

def test_chronology_validation():
    # Valid chronological order
    is_valid, violations = ClinicalVerifier.validate_chronology(
        dob="1978-06-15",
        referral_date="2024-03-01",
        service_date="2024-03-20"
    )
    assert is_valid
    assert len(violations) == 0
    print("[PASS] test_chronology_validation: standard chronological flow verified.")

    # Violation 1: DOB after referral date
    is_valid, violations = ClinicalVerifier.validate_chronology(
        dob="2025-01-01",
        referral_date="2024-01-01"
    )
    assert not is_valid
    assert any("must precede referral" in v for v in violations)

    # Violation 2: Referral date far in future
    is_valid, violations = ClinicalVerifier.validate_chronology(
        dob="1990-01-01",
        referral_date="2099-01-01"
    )
    assert not is_valid
    assert any("post-dated beyond 7 days" in v for v in violations)

    # Violation 3: Service date exceeds 1 year window
    is_valid, violations = ClinicalVerifier.validate_chronology(
        dob="1990-01-01",
        referral_date="2024-01-01",
        service_date="2026-05-01"
    )
    assert not is_valid
    assert any("exceeds 1 year referral validity window" in v for v in violations)
    print("[PASS] test_chronology_validation: all temporal invariants rejected correctly.")

if __name__ == "__main__":
    test_npi_luhn_validation()
    test_icd10_taxonomy_validation()
    test_chronology_validation()
    print("\nALL CLINICAL VERIFIER TESTS PASSED (100%)!")
