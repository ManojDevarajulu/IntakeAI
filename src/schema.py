import re
from datetime import date
from typing import Dict, Any, Optional, List, Generic, TypeVar
from pydantic import BaseModel, Field, field_validator

T = TypeVar("T")

class BoundingBox(BaseModel):
    """Normalized document coordinates: [0.0, 1.0]."""
    ymin: float = Field(..., ge=0.0, le=1.0, description="Top-edge relative Y coordinate")
    xmin: float = Field(..., ge=0.0, le=1.0, description="Left-edge relative X coordinate")
    ymax: float = Field(..., ge=0.0, le=1.0, description="Bottom-edge relative Y coordinate")
    xmax: float = Field(..., ge=0.0, le=1.0, description="Right-edge relative X coordinate")
    page: int = Field(1, ge=1, description="1-indexed document page number")

    @field_validator("ymax")
    @classmethod
    def validate_y_order(cls, v, info):
        ymin = info.data.get("ymin", 0.0)
        if v < ymin:
            raise ValueError(f"ymax ({v}) cannot be less than ymin ({ymin})")
        return v

    @field_validator("xmax")
    @classmethod
    def validate_x_order(cls, v, info):
        xmin = info.data.get("xmin", 0.0)
        if v < xmin:
            raise ValueError(f"xmax ({v}) cannot be less than xmin ({xmin})")
        return v

class ClinicalEntity(BaseModel, Generic[T]):
    """Extracted clinical field with pixel coordinates and confidence scoring."""
    value: T
    raw_text: str = Field(..., description="Exact raw text span extracted from OCR")
    bbox: Optional[BoundingBox] = None
    confidence: float = Field(1.0, ge=0.0, le=1.0, description="Conformal calibration score")
    status: str = Field("PENDING", description="'AUTO_ACCEPTED', 'FLAGGED_FOR_REVIEW', or 'OVERRIDDEN'")
    validation_note: Optional[str] = None

class PatientDemographics(BaseModel):
    """Patient demographics conforming to US Core Patient profile."""
    first_name: str
    last_name: str
    dob: str = Field(..., description="Date of birth in YYYY-MM-DD format")
    gender: str = Field("unknown", description="'male', 'female', 'other', or 'unknown'")
    phone: Optional[str] = None
    mrn: Optional[str] = None

    @field_validator("dob")
    @classmethod
    def validate_dob_format(cls, v):
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", v):
            raise ValueError(f"Date of birth must be YYYY-MM-DD, got '{v}'")
        return v

class InsuranceCoverage(BaseModel):
    """Health insurance policy information."""
    payer_name: str
    member_id: str
    group_number: Optional[str] = None

class ProviderInfo(BaseModel):
    """Healthcare provider demographics with 10-digit NPI."""
    name: str
    npi: str = Field(..., description="10-digit National Provider Identifier")
    clinic_name: Optional[str] = None
    phone: Optional[str] = None
    fax: Optional[str] = None

    @field_validator("npi")
    @classmethod
    def validate_npi_digits(cls, v):
        clean = re.sub(r"\D", "", v)
        if len(clean) != 10:
            raise ValueError(f"NPI must contain exactly 10 digits, got '{v}' ({len(clean)} digits)")
        return clean

class ClinicalDiagnosis(BaseModel):
    """Clinical diagnosis coding."""
    code: str = Field(..., description="ICD-10-CM diagnosis code (e.g. 'E11.9', 'I10')")
    description: str = Field(..., description="Clinical terminology text")
    is_primary: bool = Field(True, description="Primary referral reason")

    @field_validator("code")
    @classmethod
    def normalize_code(cls, v):
        return v.strip().upper()

class ReferralV1(BaseModel):
    """
    Standardized Clinical Referral Document Schema (ReferralV1).
    Serves as the internal data contract across Ingestion, Verification, and FHIR export.
    """
    referral_id: str = Field(..., description="Unique intake identifier")
    source_file: str = Field(..., description="Original filename (e.g., 'referral_fax_102.pdf')")
    referral_date: str = Field(..., description="Date of referral generation (YYYY-MM-DD)")
    requested_service_date: Optional[str] = Field(None, description="Requested appointment date")
    service_requested: str = Field(..., description="Requested specialty consult or diagnostic procedure")
    urgency: str = Field("ROUTINE", description="'ROUTINE', 'URGENT', or 'STAT'")
    
    patient: PatientDemographics
    insurance: Optional[InsuranceCoverage] = None
    referring_provider: ProviderInfo
    servicing_provider: Optional[ProviderInfo] = None
    diagnoses: List[ClinicalDiagnosis] = Field(default_factory=list)
    clinical_notes: Optional[str] = None

    # Audit & Coordinate Tracking Layer
    field_entities: Dict[str, ClinicalEntity[Any]] = Field(
        default_factory=dict,
        description="Coordinates and calibration metrics for each individual field"
    )

    # Human-in-the-Loop Routing Metadata
    routing_decision: str = Field("PENDING", description="'AUTO_ACCEPTED' or 'FLAGGED_FOR_REVIEW'")
    overall_confidence: float = Field(1.0, ge=0.0, le=1.0)
    validation_flags: List[str] = Field(
        default_factory=list,
        description="List of failing checks (e.g. 'INVALID_NPI', 'CHRONOLOGY_MISMATCH')"
    )
