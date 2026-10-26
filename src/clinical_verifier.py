import re
from datetime import datetime, date, timedelta
from typing import Tuple, Optional, Dict, Any, List

class ClinicalVerifier:
    """
    Deterministic Invariant Verification Engine for Clinical Referrals.
    
    Implements mathematical, taxonomic, and temporal checks that execute
    with zero hallucination, serving as the deterministic foundation for IDP routing.
    """

    # CMS ISO/IEC 7812 Healthcare Identifier constant prefix sum
    # Prefix: '80840' -> (8*1 + 0*2 + 8*1 + 4*2 + 0*1) = 8 + 0 + 8 + 8 + 0 = 24
    NPI_PREFIX_CONSTANT = 24

    # ICD-10-CM Format Pattern (WHO / CMS Standard)
    ICD10_REGEX = re.compile(r"^[A-TV-Z][0-9][0-9A-B](\.[0-9A-TV-Z]{1,4})?$", re.IGNORECASE)

    # Curated High-Frequency Clinical Codes (CMS Outpatient / Specialty Taxonomy)
    ICD10_TAXONOMY: Dict[str, str] = {
        # Endocrine & Metabolic
        "E11.9": "Type 2 diabetes mellitus without complications",
        "E11.65": "Type 2 diabetes mellitus with hyperglycemia",
        "E03.9": "Hypothyroidism, unspecified",
        "E78.5": "Hyperlipidemia, unspecified",
        "E66.01": "Morbid (severe) obesity due to excess calories",
        
        # Circulatory / Cardiovascular
        "I10": "Essential (primary) hypertension",
        "I25.10": "Atherosclerotic heart disease of native coronary artery",
        "I50.9": "Heart failure, unspecified",
        "I48.91": "Unspecified atrial fibrillation",
        "I73.9": "Peripheral vascular disease, unspecified",

        # Musculoskeletal & Orthopedic
        "M54.5": "Low back pain",
        "M54.50": "Low back pain, unspecified",
        "M17.11": "Primary osteoarthritis, right knee",
        "M17.12": "Primary osteoarthritis, left knee",
        "M25.561": "Pain in right knee",
        "M25.562": "Pain in left knee",
        "M75.10": "Rotator cuff tear or rupture, unspecified shoulder",
        "M54.2": "Cervicalgia (neck pain)",

        # Respiratory
        "J45.909": "Unspecified asthma, uncomplicated",
        "J44.9": "Chronic obstructive pulmonary disease, unspecified",
        "J01.90": "Acute sinusitis, unspecified",
        "J18.9": "Pneumonia, unspecified organism",

        # Oncology & Hematology
        "C50.919": "Malignant neoplasm of unspecified site of female breast",
        "C34.90": "Malignant neoplasm of unspecified part of bronchus or lung",
        "C61": "Malignant neoplasm of prostate",
        "D64.9": "Anemia, unspecified",

        # Neurology & Sleep
        "G43.909": "Migraine, unspecified, not intractable",
        "G47.33": "Obstructive sleep apnea (adult)",
        "G40.909": "Epilepsy, unspecified, not intractable",

        # Gastroenterology
        "K21.9": "Gastro-esophageal reflux disease without esophagitis",
        "K58.0": "Irritable bowel syndrome with diarrhea",
        "K57.90": "Diverticulosis of colon without perforation or abscess",

        # Behavioral & General Encounters
        "F41.1": "Generalized anxiety disorder",
        "F32.9": "Major depressive disorder, single episode, unspecified",
        "Z00.00": "Encounter for general adult medical examination without abnormal findings",
        "Z12.31": "Encounter for screening mammogram for malignant neoplasm of breast",
        "Z96.651": "Presence of right artificial knee joint"
    }

    @classmethod
    def validate_npi(cls, npi: str) -> Tuple[bool, str]:
        """
        Validates a 10-digit National Provider Identifier (NPI) using the official
        US CMS check-digit algorithm (Luhn algorithm with '80840' prefix).
        
        Returns:
            Tuple[bool, str]: (is_valid, descriptive_message)
        """
        clean_npi = re.sub(r"\D", "", str(npi).strip())
        
        if len(clean_npi) != 10:
            return False, f"NPI must contain exactly 10 digits (got {len(clean_npi)})"

        # The 10th digit is the check digit
        # Weights from right: d10*1, d9*2, d8*1, d7*2, d6*1, d5*2, d4*1, d3*2, d2*1, d1*2
        weights = [2, 1, 2, 1, 2, 1, 2, 1, 2, 1]
        digit_sum = 0
        
        for i, char in enumerate(clean_npi):
            val = int(char) * weights[i]
            # If doubling results in two digits (e.g. 14), sum the digits: 1 + 4 = 5 (or val - 9)
            if val > 9:
                val = val - 9
            digit_sum += val

        total_sum = digit_sum + cls.NPI_PREFIX_CONSTANT

        if total_sum % 10 == 0:
            return True, "Valid 10-digit CMS NPI"
        else:
            return False, f"Invalid NPI Luhn check digit (total modulo {total_sum % 10} != 0)"

    @classmethod
    def validate_icd10(cls, code: str) -> Tuple[bool, str, Optional[str]]:
        """
        Validates an ICD-10-CM diagnosis code against syntax and CMS taxonomy.
        
        Returns:
            Tuple[bool, str, Optional[str]]: (is_valid, validation_message, description_or_none)
        """
        clean_code = code.strip().upper()
        
        if not cls.ICD10_REGEX.match(clean_code):
            return False, f"Invalid ICD-10-CM format: '{clean_code}'", None

        # Check known CMS taxonomy dictionary
        if clean_code in cls.ICD10_TAXONOMY:
            desc = cls.ICD10_TAXONOMY[clean_code]
            return True, f"Verified in CMS taxonomy: {desc}", desc

        # Valid syntactic format even if outside our high-frequency sample
        return True, "Valid ICD-10-CM syntax", None

    @classmethod
    def validate_chronology(
        cls,
        dob: str,
        referral_date: str,
        service_date: Optional[str] = None
    ) -> Tuple[bool, List[str]]:
        """
        Validates temporal consistency across clinical dates.
        Invariants:
        1. Patient DOB must precede the referral date.
        2. If service date is given, DOB must precede service date.
        3. Referral date cannot be post-dated (> 7 days in the future).
        4. Service date should fall within -30 to +365 days of referral.
        
        Returns:
            Tuple[bool, List[str]]: (is_valid, list_of_violations)
        """
        violations = []

        try:
            d_dob = datetime.strptime(dob, "%Y-%m-%d").date()
        except ValueError:
            return False, [f"Invalid DOB date format: '{dob}', expected YYYY-MM-DD"]

        try:
            d_ref = datetime.strptime(referral_date, "%Y-%m-%d").date()
        except ValueError:
            return False, [f"Invalid Referral Date format: '{referral_date}', expected YYYY-MM-DD"]

        today = date.today()

        # Invariant 1: DOB before referral
        if d_dob >= d_ref:
            violations.append(f"Patient DOB ({dob}) must precede referral date ({referral_date})")

        # Invariant 2: Referral date cannot be far in future
        if d_ref > today + timedelta(days=7):
            violations.append(f"Referral date ({referral_date}) is post-dated beyond 7 days in future")

        if service_date:
            try:
                d_srv = datetime.strptime(service_date, "%Y-%m-%d").date()
                if d_dob >= d_srv:
                    violations.append(f"Patient DOB ({dob}) must precede requested service date ({service_date})")
                
                # Service date vs referral date window (-30 days to +365 days)
                if d_srv < d_ref - timedelta(days=30):
                    violations.append(f"Service date ({service_date}) is over 30 days prior to referral ({referral_date})")
                elif d_srv > d_ref + timedelta(days=365):
                    violations.append(f"Service date ({service_date}) exceeds 1 year referral validity window")
            except ValueError:
                violations.append(f"Invalid Service Date format: '{service_date}', expected YYYY-MM-DD")

        return (len(violations) == 0), violations
