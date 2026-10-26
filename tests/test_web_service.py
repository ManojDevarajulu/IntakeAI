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
    test_api_static_index()
    print("\nALL WEB SERVICE & API TESTS PASSED (100%)!")
