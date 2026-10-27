"""Integration Tests for FastAPI Web Service and REST Endpoints."""

import json
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi.testclient import TestClient
from web.server import app

client = TestClient(app)


def test_api_health():
    res = client.get("/api/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "HEALTHY"
    assert data["queue_depth"] > 0
    assert "conformal_thresholds" in data
    print("[PASS] test_api_health")


def test_api_referrals():
    res = client.get("/api/referrals")
    assert res.status_code == 200
    data = res.json()
    assert "referrals" in data
    assert len(data["referrals"]) > 0

    first = data["referrals"][0]
    assert "referral_id" in first
    assert "patient_name" in first
    assert "npi" in first
    assert "routing_decision" in first
    print("[PASS] test_api_referrals")


def test_api_referral_detail_and_image():
    res_list = client.get("/api/referrals")
    ref_id = res_list.json()["referrals"][0]["referral_id"]

    res_detail = client.get(f"/api/referrals/{ref_id}")
    assert res_detail.status_code == 200
    detail = res_detail.json()
    assert detail["referral_id"] == ref_id
    assert "field_entities" in detail
    assert "audit" in detail

    res_img = client.get(f"/api/referrals/{ref_id}/image")
    assert res_img.status_code == 200
    assert res_img.headers["content-type"] == "image/png"
    assert len(res_img.content) > 1000
    print("[PASS] test_api_referral_detail_and_image")


def test_api_approve():
    res_list = client.get("/api/referrals")
    # Find a flagged case
    flagged = next(r for r in res_list.json()["referrals"] if r["routing_decision"] != "AUTO_ACCEPTED")
    flag_id = flagged["referral_id"]

    res_app = client.post(
        "/api/review/approve",
        json={"referral_id": flag_id, "override_notes": "Verified by Medical Director"},
    )
    assert res_app.status_code == 200
    data = res_app.json()
    assert data["status"] == "SUCCESS"
    assert data["new_decision"] == "APPROVED_BY_CLINICIAN"

    # Verify state in detail
    detail = client.get(f"/api/referrals/{flag_id}").json()
    assert detail["clinician_approved"] is True
    assert detail["clinician_notes"] == "Verified by Medical Director"
    print("[PASS] test_api_approve")


def test_api_fhir_export():
    res_list = client.get("/api/referrals")
    ref_id = res_list.json()["referrals"][0]["referral_id"]

    res_fhir = client.get(f"/api/referrals/{ref_id}/fhir")
    assert res_fhir.status_code == 200
    data = res_fhir.json()
    assert data["is_valid"] is True
    assert data["bundle"]["resourceType"] == "Bundle"
    assert data["bundle"]["total"] >= 4
    print("[PASS] test_api_fhir_export")


def test_api_benchmark_endpoint():
    res = client.get("/api/benchmark")
    assert res.status_code == 200
    metrics = res.json()
    assert metrics["stp_rate_clean"] >= 75.0
    assert metrics["safety_catch_npi_luhn"] == 100.0
    assert metrics["overall_safety_sensitivity"] == 100.0
    print("[PASS] test_api_benchmark_endpoint")


def test_api_samples_and_upload():
    # 1. List samples
    res = client.get("/api/intake/samples")
    assert res.status_code == 200
    samples = res.json()["samples"]
    assert len(samples) >= 6
    filenames = [s["filename"] for s in samples]
    assert "01_clean_cardiology_referral.png" in filenames
    assert "06_clinical_referral.pdf" in filenames

    # 2. Ingest sample clean cardiology
    res_clean = client.post("/api/intake/load_sample", json={"filename": "01_clean_cardiology_referral.png"})
    assert res_clean.status_code == 200
    assert res_clean.json()["status"] == "SUCCESS"

    # 3. Ingest PDF document
    res_pdf = client.post("/api/intake/load_sample", json={"filename": "06_clinical_referral.pdf"})
    assert res_pdf.status_code == 200
    assert res_pdf.json()["status"] == "SUCCESS"
    assert res_pdf.json()["decision"] in ("AUTO_ACCEPTED", "FLAGGED_FOR_REVIEW")

    # 4. Ingest NPI error document
    res_err = client.post("/api/intake/load_sample", json={"filename": "02_npi_luhn_error_referral.png"})
    assert res_err.status_code == 200
    assert res_err.json()["decision"] == "FLAGGED_FOR_REVIEW"

    print("[PASS] test_api_samples_and_upload")


def test_api_field_edit():
    # Load NPI error referral
    res_err = client.post("/api/intake/load_sample", json={"filename": "02_npi_luhn_error_referral.png"})
    ref_id = res_err.json()["referral_id"]
    assert res_err.json()["decision"] == "FLAGGED_FOR_REVIEW"

    # Edit NPI to valid check-digit 1497758544
    res_edit = client.put(f"/api/referrals/{ref_id}/field", json={
        "field_key": "referring_provider.npi",
        "new_value": "1497758544",
    })
    assert res_edit.status_code == 200
    edit_data = res_edit.json()
    assert edit_data["status"] == "SUCCESS"
    assert edit_data["updated_field"] == "referring_provider.npi"
    assert edit_data["decision"] in ("AUTO_ACCEPTED", "FLAGGED_FOR_REVIEW")
    assert not any("NPI" in f for f in edit_data["flags"])

    print("[PASS] test_api_field_edit")


def test_api_system_info():
    res = client.get("/api/system/info")
    assert res.status_code == 200
    info = res.json()
    assert "system" in info
    assert "ocr_engine" in info
    assert "llm_engine" in info
    assert "deterministic_invariants" in info
    assert "conformal_router" in info
    assert "ehr_fhir" in info
    print("[PASS] test_api_system_info")


def test_api_static_index():
    res = client.get("/")
    assert res.status_code == 200
    assert "Intake AI" in res.text
    print("[PASS] test_api_static_index")


if __name__ == "__main__":
    test_api_health()
    test_api_referrals()
    test_api_referral_detail_and_image()
    test_api_approve()
    test_api_fhir_export()
    test_api_benchmark_endpoint()
    test_api_samples_and_upload()
    test_api_field_edit()
    test_api_system_info()
    test_api_static_index()
    print("\nALL WEB SERVICE & API TESTS PASSED (100%)!")
