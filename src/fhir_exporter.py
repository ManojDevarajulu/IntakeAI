"""HL7 FHIR R4 Bundle Exporter for Clinical Referrals.

Transforms approved and verified ReferralV1 intake records into validated
HL7 FHIR R4 standard JSON transaction bundles conforming to US Core profiles:
- US Core Patient
- US Core Practitioner (with 10-digit NPI identifier)
- US Core Condition (with ICD-10-CM diagnosis coding)
- US Core ServiceRequest (referral order)
- FHIR Coverage (payer & subscriber policy)
"""

from __future__ import annotations

import json
import uuid
from typing import Any, Dict, List, Optional
from datetime import datetime

from src.schema import ReferralV1


class FHIRExporter:
    """Exports ReferralV1 records to standard HL7 FHIR R4 JSON Bundles."""

    @staticmethod
    def export_bundle(
        referral: ReferralV1,
        bundle_type: str = "transaction",
    ) -> Dict[str, Any]:
        """Converts an approved or reviewed ReferralV1 instance into an HL7 FHIR R4 bundle."""
        patient_uuid = f"urn:uuid:{uuid.uuid5(uuid.NAMESPACE_DNS, f'pat-{referral.patient.last_name}-{referral.patient.dob}')}"
        practitioner_uuid = f"urn:uuid:{uuid.uuid5(uuid.NAMESPACE_DNS, f'prac-{referral.referring_provider.npi}')}"
        condition_uuid = f"urn:uuid:{uuid.uuid5(uuid.NAMESPACE_DNS, f'cond-{referral.referral_id}')}"
        coverage_uuid = f"urn:uuid:{uuid.uuid5(uuid.NAMESPACE_DNS, f'cov-{referral.referral_id}')}"
        service_req_uuid = f"urn:uuid:{uuid.uuid5(uuid.NAMESPACE_DNS, f'sr-{referral.referral_id}')}"

        entries: List[Dict[str, Any]] = []

        # -------------------------------------------------------------
        # 1. US Core Patient Resource
        # -------------------------------------------------------------
        patient_resource: Dict[str, Any] = {
            "resourceType": "Patient",
            "id": patient_uuid.replace("urn:uuid:", ""),
            "meta": {
                "profile": ["http://hl7.org/fhir/us/core/StructureDefinition/us-core-patient"]
            },
            "name": [
                {
                    "use": "official",
                    "family": referral.patient.last_name,
                    "given": [referral.patient.first_name],
                }
            ],
            "birthDate": referral.patient.dob,
            "gender": referral.patient.gender if referral.patient.gender in ["male", "female", "other", "unknown"] else "unknown",
        }
        if referral.patient.phone:
            patient_resource["telecom"] = [
                {"system": "phone", "value": referral.patient.phone, "use": "home"}
            ]
        if referral.patient.mrn:
            patient_resource["identifier"] = [
                {"system": "http://hospital.example.org/mrn", "value": referral.patient.mrn}
            ]

        entries.append({
            "fullUrl": patient_uuid,
            "resource": patient_resource,
            "request": {"method": "POST", "url": "Patient"},
        })

        # -------------------------------------------------------------
        # 2. US Core Practitioner Resource (NPI)
        # -------------------------------------------------------------
        practitioner_resource: Dict[str, Any] = {
            "resourceType": "Practitioner",
            "id": practitioner_uuid.replace("urn:uuid:", ""),
            "meta": {
                "profile": ["http://hl7.org/fhir/us/core/StructureDefinition/us-core-practitioner"]
            },
            "identifier": [
                {
                    "system": "http://hl7.org/fhir/sid/us-npi",
                    "value": referral.referring_provider.npi,
                }
            ],
            "name": [{"text": referral.referring_provider.name}],
        }
        telecoms = []
        if referral.referring_provider.phone:
            telecoms.append({"system": "phone", "value": referral.referring_provider.phone, "use": "work"})
        if referral.referring_provider.fax:
            telecoms.append({"system": "fax", "value": referral.referring_provider.fax, "use": "work"})
        if telecoms:
            practitioner_resource["telecom"] = telecoms

        entries.append({
            "fullUrl": practitioner_uuid,
            "resource": practitioner_resource,
            "request": {"method": "POST", "url": "Practitioner"},
        })

        # -------------------------------------------------------------
        # 3. Health Insurance Coverage Resource
        # -------------------------------------------------------------
        if referral.insurance:
            coverage_resource: Dict[str, Any] = {
                "resourceType": "Coverage",
                "id": coverage_uuid.replace("urn:uuid:", ""),
                "status": "active",
                "beneficiary": {"reference": patient_uuid},
                "payor": [{"display": referral.insurance.payer_name}],
                "subscriberId": referral.insurance.member_id,
            }
            if referral.insurance.group_number:
                coverage_resource["class"] = [
                    {"type": {"coding": [{"code": "group"}]}, "value": referral.insurance.group_number}
                ]
            entries.append({
                "fullUrl": coverage_uuid,
                "resource": coverage_resource,
                "request": {"method": "POST", "url": "Coverage"},
            })

        # -------------------------------------------------------------
        # 4. US Core Condition (ICD-10-CM Diagnosis)
        # -------------------------------------------------------------
        primary_diag = referral.primary_diagnosis
        if primary_diag:
            condition_resource: Dict[str, Any] = {
                "resourceType": "Condition",
                "id": condition_uuid.replace("urn:uuid:", ""),
                "meta": {
                    "profile": ["http://hl7.org/fhir/us/core/StructureDefinition/us-core-condition-encounter-diagnosis"]
                },
                "clinicalStatus": {
                    "coding": [
                        {
                            "system": "http://terminology.hl7.org/CodeSystem/condition-clinical",
                            "code": "active",
                        }
                    ]
                },
                "verificationStatus": {
                    "coding": [
                        {
                            "system": "http://terminology.hl7.org/CodeSystem/condition-ver-status",
                            "code": "confirmed",
                        }
                    ]
                },
                "category": [
                    {
                        "coding": [
                            {
                                "system": "http://terminology.hl7.org/CodeSystem/condition-category",
                                "code": "encounter-diagnosis",
                                "display": "Encounter Diagnosis",
                            }
                        ]
                    }
                ],
                "code": {
                    "coding": [
                        {
                            "system": "http://hl7.org/fhir/sid/icd-10-cm",
                            "code": primary_diag.code,
                            "display": primary_diag.description,
                        }
                    ],
                    "text": primary_diag.description,
                },
                "subject": {"reference": patient_uuid},
            }
            entries.append({
                "fullUrl": condition_uuid,
                "resource": condition_resource,
                "request": {"method": "POST", "url": "Condition"},
            })

        # -------------------------------------------------------------
        # 5. US Core ServiceRequest (Referral Order)
        # -------------------------------------------------------------
        priority_map = {
            "ROUTINE": "routine",
            "URGENT": "urgent",
            "STAT": "stat",
        }
        service_req_resource: Dict[str, Any] = {
            "resourceType": "ServiceRequest",
            "id": service_req_uuid.replace("urn:uuid:", ""),
            "meta": {
                "profile": ["http://hl7.org/fhir/us/core/StructureDefinition/us-core-servicerequest"]
            },
            "identifier": [
                {
                    "system": "http://intake-ai.hospital.org/referrals",
                    "value": referral.referral_id,
                }
            ],
            "status": "active",
            "intent": "order",
            "priority": priority_map.get(referral.urgency.upper(), "routine"),
            "code": {
                "text": referral.service_requested,
            },
            "subject": {"reference": patient_uuid},
            "requester": {"reference": practitioner_uuid},
            "authoredOn": f"{referral.referral_date}T00:00:00Z",
        }
        if primary_diag:
            service_req_resource["reasonReference"] = [{"reference": condition_uuid}]
        if referral.requested_service_date:
            service_req_resource["occurrenceDateTime"] = f"{referral.requested_service_date}T00:00:00Z"

        entries.append({
            "fullUrl": service_req_uuid,
            "resource": service_req_resource,
            "request": {"method": "POST", "url": "ServiceRequest"},
        })

        # -------------------------------------------------------------
        # Assemble FHIR Bundle
        # -------------------------------------------------------------
        bundle = {
            "resourceType": "Bundle",
            "id": f"bundle-{referral.referral_id.lower().replace('_', '-')}",
            "type": bundle_type,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "total": len(entries),
            "entry": entries,
        }

        return bundle

    @staticmethod
    def validate_bundle_structure(bundle: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """Lightweight schema compliance validator for exported FHIR bundles."""
        errors: List[str] = []

        if bundle.get("resourceType") != "Bundle":
            errors.append("Root resource must be 'Bundle'")

        if "type" not in bundle:
            errors.append("Bundle missing 'type' element")

        entries = bundle.get("entry", [])
        if not entries:
            errors.append("Bundle contains no entries")

        resource_types = [e.get("resource", {}).get("resourceType") for e in entries]
        for expected in ["Patient", "Practitioner", "ServiceRequest"]:
            if expected not in resource_types:
                errors.append(f"Bundle missing required resource: {expected}")

        return len(errors) == 0, errors
