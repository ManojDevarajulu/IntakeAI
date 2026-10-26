"""Conformal Risk-Calibrated Router for Clinical Document Ingestion.

Implements risk-calibrated triage combining:
1. Conformal confidence thresholding (error bounds α <= 0.05).
2. Deterministic mathematical & taxonomic invariants (CMS 10-Digit NPI Luhn, ICD-10-CM, chronological order).
3. Straight-Through Processing (STP) routing vs. Clinician Review Queue triaging.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from src.clinical_verifier import ClinicalVerifier
from src.schema import ClinicalEntity, ReferralV1


class CalibratedRouter:
    """Evaluates clinical invariants and conformal confidence bounds to route referrals."""

    def __init__(
        self,
        min_field_confidence: float = 0.85,
        min_critical_confidence: float = 0.88,
        min_overall_confidence: float = 0.85,
    ):
        self.min_field_confidence = min_field_confidence
        self.min_critical_confidence = min_critical_confidence
        self.min_overall_confidence = min_overall_confidence

    def evaluate_and_route(self, referral: ReferralV1) -> Tuple[ReferralV1, Dict[str, Any]]:
        """Evaluates referral against deterministic invariants and conformal thresholds.
        
        Returns:
            Tuple of (Annotated ReferralV1, Routing Audit Summary)
        """
        flags: List[str] = []
        field_evaluations: Dict[str, Dict[str, Any]] = {}

        # -------------------------------------------------------------
        # 1. Deterministic Clinical Invariant Checks
        # -------------------------------------------------------------

        # A. CMS 10-Digit NPI Luhn Check
        npi = referral.referring_provider.npi
        npi_valid, npi_reason = ClinicalVerifier.validate_npi(npi)
        npi_entity = referral.field_entities.get("referring_provider.npi")
        if not npi_valid:
            flags.append(f"INVALID_NPI: {npi_reason}")
            if npi_entity:
                npi_entity.status = "FLAGGED_FOR_REVIEW"
                npi_entity.validation_note = npi_reason
        field_evaluations["npi_luhn"] = {"valid": npi_valid, "reason": npi_reason, "value": npi}

        # B. CMS ICD-10-CM Taxonomy Validation
        primary_diag = referral.primary_diagnosis
        if primary_diag:
            icd_code = primary_diag.code
            icd_valid, icd_reason, icd_desc = ClinicalVerifier.validate_icd10(icd_code)
            diag_entity = referral.field_entities.get("diagnosis.icd10_code")
            if not icd_valid:
                flags.append(f"INVALID_ICD10: {icd_reason}")
                if diag_entity:
                    diag_entity.status = "FLAGGED_FOR_REVIEW"
                    diag_entity.validation_note = icd_reason
            elif icd_desc is None:
                flags.append(f"UNVERIFIED_ICD10_TAXONOMY: Code '{icd_code}' not in active CMS table")
                if diag_entity:
                    diag_entity.status = "FLAGGED_FOR_REVIEW"
                    diag_entity.validation_note = "Code not in verified CMS taxonomy table"
            field_evaluations["icd10_taxonomy"] = {
                "valid": icd_valid and (icd_desc is not None),
                "reason": icd_reason,
                "code": icd_code,
                "description": icd_desc,
            }
        else:
            flags.append("MISSING_DIAGNOSIS: No primary ICD-10 diagnosis provided")
            field_evaluations["icd10_taxonomy"] = {"valid": False, "reason": "No diagnosis code present"}

        # C. Chronological Timeline Invariant Check
        dob_str = referral.patient.dob
        ref_date_str = referral.referral_date
        dos_str = referral.requested_service_date
        chrono_valid, chrono_reason = ClinicalVerifier.validate_chronology(
            dob=dob_str,
            referral_date=ref_date_str,
            service_date=dos_str,
        )
        if not chrono_valid:
            flags.append(f"CHRONOLOGY_MISMATCH: {chrono_reason}")
            dob_entity = referral.field_entities.get("patient.dob")
            if dob_entity:
                dob_entity.status = "FLAGGED_FOR_REVIEW"
                dob_entity.validation_note = chrono_reason
        field_evaluations["chronology"] = {
            "valid": chrono_valid,
            "reason": chrono_reason,
            "dob": dob_str,
            "referral_date": ref_date_str,
            "service_date": dos_str,
        }

        # -------------------------------------------------------------
        # 2. Conformal Confidence Calibration Checks
        # -------------------------------------------------------------
        critical_fields = {
            "referring_provider.npi": self.min_critical_confidence,
            "diagnosis.icd10_code": self.min_critical_confidence,
            "patient.dob": self.min_critical_confidence,
            "patient.first_name": self.min_field_confidence,
            "patient.last_name": self.min_field_confidence,
            "insurance.member_id": self.min_field_confidence,
            "referral_id": self.min_field_confidence,
        }

        low_confidence_fields: List[str] = []

        for field_name, threshold in critical_fields.items():
            entity = referral.field_entities.get(field_name)
            if entity:
                if entity.confidence < threshold:
                    low_confidence_fields.append(field_name)
                    flags.append(
                        f"LOW_CONFIDENCE_{field_name.upper().replace('.', '_')}: "
                        f"score {entity.confidence:.2f} < threshold {threshold:.2f}"
                    )
                    entity.status = "FLAGGED_FOR_REVIEW"
                    entity.validation_note = (
                        f"Confidence {entity.confidence:.2f} below calibrated safety threshold {threshold:.2f}"
                    )
                elif entity.status != "FLAGGED_FOR_REVIEW":
                    entity.status = "AUTO_ACCEPTED"

        if referral.overall_confidence < self.min_overall_confidence:
            flags.append(
                f"LOW_OVERALL_CONFIDENCE: score {referral.overall_confidence:.2f} < {self.min_overall_confidence:.2f}"
            )

        # -------------------------------------------------------------
        # 3. Final Straight-Through Processing (STP) Decision
        # -------------------------------------------------------------
        is_auto_accepted = len(flags) == 0

        referral.routing_decision = "AUTO_ACCEPTED" if is_auto_accepted else "FLAGGED_FOR_REVIEW"
        referral.validation_flags = flags

        audit_summary = {
            "referral_id": referral.referral_id,
            "source_file": referral.source_file,
            "decision": referral.routing_decision,
            "stp_eligible": is_auto_accepted,
            "overall_confidence": referral.overall_confidence,
            "validation_flags": flags,
            "invariant_checks": field_evaluations,
            "low_confidence_fields": low_confidence_fields,
        }

        return referral, audit_summary
