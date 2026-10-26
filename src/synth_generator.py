"""Synthetic Clinical Referral Generator & Analog Fax Degradation Pipeline.

Generates realistic ambulatory consultation and medical referral forms
with exact normalized spatial bounding box ground truth [ymin, xmin, ymax, xmax],
and applies deterministic multi-stage analog fax degradation (skew, sensor streaks,
salt-and-pepper noise, CCITT G3/G4 binarization).
"""

from __future__ import annotations

import json
import math
import random
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from src.schema import (
    BoundingBox,
    ClinicalDiagnosis,
    ClinicalEntity,
    InsuranceCoverage,
    PatientDemographics,
    ProviderInfo,
    ReferralV1,
)


class SyntheticFaxGenerator:
    """Renders clinical referral documents and applies realistic analog fax degradation."""

    def __init__(self, width: int = 1200, height: int = 1600):
        self.width = width
        self.height = height
        self._init_fonts()

    def _init_fonts(self) -> None:
        """Loads system fonts with graceful fallback to Pillow bitmap defaults."""
        try:
            self.font_header = ImageFont.truetype("arial.ttf", 24)
            self.font_title = ImageFont.truetype("arial.ttf", 18)
            self.font_section = ImageFont.truetype("arial.ttf", 14)
            self.font_label = ImageFont.truetype("arial.ttf", 12)
            self.font_value = ImageFont.truetype("arial.ttf", 13)
            self.font_mono = ImageFont.truetype("arial.ttf", 13)
            self.font_fine = ImageFont.truetype("arial.ttf", 10)
        except Exception:
            default = ImageFont.load_default()
            self.font_header = default
            self.font_title = default
            self.font_section = default
            self.font_label = default
            self.font_value = default
            self.font_mono = default
            self.font_fine = default

    def _norm_box(self, x0: float, y0: float, x1: float, y1: float) -> BoundingBox:
        """Converts raw pixel coordinates to normalized [ymin, xmin, ymax, xmax] in [0, 1]."""
        ymin = max(0.0, min(1.0, y0 / self.height))
        xmin = max(0.0, min(1.0, x0 / self.width))
        ymax = max(0.0, min(1.0, y1 / self.height))
        xmax = max(0.0, min(1.0, x1 / self.width))
        # Ensure non-zero height/width
        if ymax <= ymin:
            ymax = min(1.0, ymin + 0.005)
        if xmax <= xmin:
            xmax = min(1.0, xmin + 0.005)
        return BoundingBox(ymin=ymin, xmin=xmin, ymax=ymax, xmax=xmax)

    def render_referral(self, record: Dict[str, Any]) -> Tuple[Image.Image, ReferralV1]:
        """Renders a clinical referral document and computes exact ground-truth bounding boxes."""
        img = Image.new("RGB", (self.width, self.height), color=(255, 255, 255))
        draw = ImageDraw.Draw(img)

        # Margin and layout anchors
        margin = 60
        y = 40

        # --- Top Fax Header Banner ---
        draw.text(
            (margin, y),
            "TRANSMITTED VIA SECURE CLINICAL FACSIMILE  |  CONFIDENTIAL HEALTHCARE COMMUNICATION",
            font=self.font_fine,
            fill=(80, 80, 80),
        )
        y += 20
        draw.line([(margin, y), (self.width - margin, y)], fill=(120, 120, 120), width=1)
        y += 18

        # Clinic Header / Hospital Brand
        draw.text(
            (margin, y),
            "AMBULATORY CARE NETWORK — SPECIALTY REFERRAL INTAKE",
            font=self.font_header,
            fill=(20, 20, 20),
        )
        y += 32
        draw.text(
            (margin, y),
            "Standard Outpatient Consultation & Clinical Transfer Order",
            font=self.font_title,
            fill=(60, 60, 60),
        )
        y += 28
        draw.line([(margin, y), (self.width - margin, y)], fill=(40, 40, 40), width=2)
        y += 20

        # Referral Metadata Line
        ref_id = record["referral_id"]
        ref_date = record["referral_date"]
        urgency = record["urgency"].upper()

        draw.text((margin, y), "Referral ID:", font=self.font_label, fill=(100, 100, 100))
        ref_id_x = margin + 85
        draw.text((ref_id_x, y), ref_id, font=self.font_mono, fill=(0, 0, 0))
        ref_id_box = self._norm_box(ref_id_x, y, ref_id_x + 140, y + 16)

        date_label_x = margin + 350
        draw.text((date_label_x, y), "Referral Date:", font=self.font_label, fill=(100, 100, 100))
        ref_date_x = date_label_x + 95
        draw.text((ref_date_x, y), ref_date, font=self.font_mono, fill=(0, 0, 0))
        ref_date_box = self._norm_box(ref_date_x, y, ref_date_x + 100, y + 16)

        urg_label_x = margin + 700
        draw.text((urg_label_x, y), "Priority / Urgency:", font=self.font_label, fill=(100, 100, 100))
        urg_x = urg_label_x + 120
        draw.text((urg_x, y), urgency, font=self.font_mono, fill=(180, 0, 0) if urgency != "ROUTINE" else (0, 0, 0))
        urgency_box = self._norm_box(urg_x, y, urg_x + 90, y + 16)

        y += 36

        # --- SECTION 1: Patient Demographics ---
        draw.rectangle([(margin, y), (self.width - margin, y + 26)], fill=(240, 240, 240))
        draw.text((margin + 10, y + 6), "1. PATIENT DEMOGRAPHICS", font=self.font_section, fill=(0, 0, 0))
        y += 38

        pat = record["patient"]
        first_name = pat["first_name"]
        last_name = pat["last_name"]
        dob = pat["dob"]
        gender = pat["gender"]
        phone = pat["phone"]
        address = pat["address"]

        # First Name & Last Name
        draw.text((margin, y), "Last Name:", font=self.font_label, fill=(80, 80, 80))
        ln_x = margin + 80
        draw.text((ln_x, y), last_name, font=self.font_value, fill=(0, 0, 0))
        ln_box = self._norm_box(ln_x, y, ln_x + 180, y + 18)

        fn_label_x = margin + 320
        draw.text((fn_label_x, y), "First Name:", font=self.font_label, fill=(80, 80, 80))
        fn_x = fn_label_x + 80
        draw.text((fn_x, y), first_name, font=self.font_value, fill=(0, 0, 0))
        fn_box = self._norm_box(fn_x, y, fn_x + 180, y + 18)

        y += 30
        # DOB & Gender
        draw.text((margin, y), "Date of Birth (YYYY-MM-DD):", font=self.font_label, fill=(80, 80, 80))
        dob_x = margin + 190
        draw.text((dob_x, y), dob, font=self.font_mono, fill=(0, 0, 0))
        dob_box = self._norm_box(dob_x, y, dob_x + 110, y + 18)

        gen_label_x = margin + 370
        draw.text((gen_label_x, y), "Gender:", font=self.font_label, fill=(80, 80, 80))
        gen_x = gen_label_x + 60
        draw.text((gen_x, y), gender.title(), font=self.font_value, fill=(0, 0, 0))
        gen_box = self._norm_box(gen_x, y, gen_x + 80, y + 18)

        y += 30
        # Phone & Address
        draw.text((margin, y), "Contact Phone:", font=self.font_label, fill=(80, 80, 80))
        phone_x = margin + 105
        draw.text((phone_x, y), phone, font=self.font_value, fill=(0, 0, 0))
        phone_box = self._norm_box(phone_x, y, phone_x + 140, y + 18)

        y += 30
        draw.text((margin, y), "Residential Address:", font=self.font_label, fill=(80, 80, 80))
        addr_x = margin + 135
        draw.text((addr_x, y), address, font=self.font_value, fill=(0, 0, 0))
        addr_box = self._norm_box(addr_x, y, addr_x + 400, y + 18)

        y += 44

        # --- SECTION 2: Insurance Coverage ---
        draw.rectangle([(margin, y), (self.width - margin, y + 26)], fill=(240, 240, 240))
        draw.text((margin + 10, y + 6), "2. PRIMARY INSURANCE COVERAGE", font=self.font_section, fill=(0, 0, 0))
        y += 38

        ins = record["insurance"]
        payer = ins["payer_name"]
        member_id = ins["member_id"]
        group_no = ins["group_number"]

        draw.text((margin, y), "Payer / Plan Name:", font=self.font_label, fill=(80, 80, 80))
        payer_x = margin + 125
        draw.text((payer_x, y), payer, font=self.font_value, fill=(0, 0, 0))
        payer_box = self._norm_box(payer_x, y, payer_x + 280, y + 18)

        mem_label_x = margin + 480
        draw.text((mem_label_x, y), "Member ID:", font=self.font_label, fill=(80, 80, 80))
        mem_x = mem_label_x + 80
        draw.text((mem_x, y), member_id, font=self.font_mono, fill=(0, 0, 0))
        mem_box = self._norm_box(mem_x, y, mem_x + 160, y + 18)

        y += 30
        draw.text((margin, y), "Group Number:", font=self.font_label, fill=(80, 80, 80))
        grp_x = margin + 100
        draw.text((grp_x, y), group_no, font=self.font_mono, fill=(0, 0, 0))
        grp_box = self._norm_box(grp_x, y, grp_x + 140, y + 18)

        y += 44

        # --- SECTION 3: Referring Provider ---
        draw.rectangle([(margin, y), (self.width - margin, y + 26)], fill=(240, 240, 240))
        draw.text((margin + 10, y + 6), "3. REFERRING CLINICIAN INFORMATION", font=self.font_section, fill=(0, 0, 0))
        y += 38

        prov = record["referring_provider"]
        prov_name = prov["provider_name"]
        npi = prov["npi"]
        clinic_name = prov["clinic_name"]
        prov_phone = prov["phone"]
        prov_fax = prov["fax"]

        draw.text((margin, y), "Provider Name:", font=self.font_label, fill=(80, 80, 80))
        prov_x = margin + 105
        draw.text((prov_x, y), prov_name, font=self.font_value, fill=(0, 0, 0))
        prov_box = self._norm_box(prov_x, y, prov_x + 240, y + 18)

        npi_label_x = margin + 450
        draw.text((npi_label_x, y), "National Provider Identifier (NPI):", font=self.font_label, fill=(80, 80, 80))
        npi_x = npi_label_x + 215
        draw.text((npi_x, y), npi, font=self.font_mono, fill=(0, 0, 0))
        npi_box = self._norm_box(npi_x, y, npi_x + 130, y + 18)

        y += 30
        draw.text((margin, y), "Practice / Facility:", font=self.font_label, fill=(80, 80, 80))
        fac_x = margin + 120
        draw.text((fac_x, y), clinic_name, font=self.font_value, fill=(0, 0, 0))
        clinic_box = self._norm_box(fac_x, y, fac_x + 300, y + 18)

        y += 30
        draw.text((margin, y), "Telephone:", font=self.font_label, fill=(80, 80, 80))
        phone_label_x = margin + 75
        draw.text((phone_label_x, y), prov_phone, font=self.font_value, fill=(0, 0, 0))
        prov_phone_box = self._norm_box(phone_label_x, y, phone_label_x + 120, y + 18)

        fax_label_x = margin + 350
        draw.text((fax_label_x, y), "Fax Number:", font=self.font_label, fill=(80, 80, 80))
        fax_x = fax_label_x + 85
        draw.text((fax_x, y), prov_fax, font=self.font_value, fill=(0, 0, 0))
        prov_fax_box = self._norm_box(fax_x, y, fax_x + 120, y + 18)

        y += 44

        # --- SECTION 4: Clinical Order & Diagnosis ---
        draw.rectangle([(margin, y), (self.width - margin, y + 26)], fill=(240, 240, 240))
        draw.text((margin + 10, y + 6), "4. CLINICAL DIAGNOSIS & REASON FOR REFERRAL", font=self.font_section, fill=(0, 0, 0))
        y += 38

        diag = record["diagnosis"]
        icd10 = diag["icd10_code"]
        diag_desc = diag["description"]
        notes = diag["clinical_notes"]

        draw.text((margin, y), "Primary ICD-10-CM Code:", font=self.font_label, fill=(80, 80, 80))
        icd_x = margin + 165
        draw.text((icd_x, y), icd10, font=self.font_mono, fill=(0, 0, 0))
        icd_box = self._norm_box(icd_x, y, icd_x + 100, y + 18)

        y += 30
        draw.text((margin, y), "Diagnosis Description:", font=self.font_label, fill=(80, 80, 80))
        desc_x = margin + 145
        draw.text((desc_x, y), diag_desc, font=self.font_value, fill=(0, 0, 0))
        desc_box = self._norm_box(desc_x, y, desc_x + 500, y + 18)

        y += 30
        svc = record["service_requested"]
        draw.text((margin, y), "Requested Specialty Service:", font=self.font_label, fill=(80, 80, 80))
        svc_x = margin + 185
        draw.text((svc_x, y), svc["service_type"], font=self.font_value, fill=(0, 0, 0))
        svc_box = self._norm_box(svc_x, y, svc_x + 350, y + 18)

        req_d_x = margin + 620
        draw.text((req_d_x, y), "Target Date:", font=self.font_label, fill=(80, 80, 80))
        target_d_x = req_d_x + 85
        draw.text((target_d_x, y), svc["requested_date"], font=self.font_mono, fill=(0, 0, 0))
        svc_date_box = self._norm_box(target_d_x, y, target_d_x + 100, y + 18)

        y += 34
        draw.text((margin, y), "Clinical Narrative / Progress Notes:", font=self.font_label, fill=(80, 80, 80))
        y += 20

        # Draw notes box
        draw.rectangle([(margin, y), (self.width - margin, y + 80)], outline=(180, 180, 180), width=1)
        draw.text((margin + 10, y + 8), notes[:130], font=self.font_value, fill=(0, 0, 0))
        if len(notes) > 130:
            draw.text((margin + 10, y + 30), notes[130:260], font=self.font_value, fill=(0, 0, 0))
        notes_box = self._norm_box(margin, y, self.width - margin, y + 80)

        y += 110

        # Footer Signoff
        draw.line([(margin, y), (margin + 300, y)], fill=(80, 80, 80), width=1)
        draw.text((margin, y + 6), f"Physician Signature: {prov_name}", font=self.font_fine, fill=(80, 80, 80))
        draw.text((margin + 600, y + 6), f"Date Executed: {ref_date}", font=self.font_fine, fill=(80, 80, 80))

        # Bottom Confidentiality Footer
        bottom_y = self.height - 50
        draw.line([(margin, bottom_y), (self.width - margin, bottom_y)], fill=(180, 180, 180), width=1)
        draw.text(
            (margin, bottom_y + 8),
            "WARNING: This facsimile contains confidential information protected by HIPAA (45 CFR § 164.530). Unauthorized distribution is prohibited.",
            font=self.font_fine,
            fill=(120, 120, 120),
        )

        # Assemble ReferralV1 with exact ground truth entities
        referral_model = ReferralV1(
            referral_id=ref_id,
            source_file=f"{ref_id}.png",
            referral_date=ref_date,
            requested_service_date=svc.get("requested_date"),
            service_requested=svc.get("service_type", "Specialty Consult"),
            urgency=record.get("urgency", "ROUTINE"),
            patient=PatientDemographics(
                first_name=first_name,
                last_name=last_name,
                dob=dob,
                gender=gender,
                phone=phone,
                mrn=record.get("patient", {}).get("mrn"),
            ),
            insurance=InsuranceCoverage(
                payer_name=payer,
                member_id=member_id,
                group_number=group_no,
            ),
            referring_provider=ProviderInfo(
                name=prov_name,
                npi=npi,
                clinic_name=clinic_name,
                phone=prov_phone,
                fax=prov_fax,
            ),
            diagnoses=[
                ClinicalDiagnosis(
                    code=icd10,
                    description=diag_desc,
                    is_primary=True,
                )
            ],
            clinical_notes=notes,
            field_entities={
                "referral_id": ClinicalEntity[str](value=ref_id, raw_text=ref_id, bbox=ref_id_box, confidence=1.0, status="AUTO_ACCEPTED"),
                "referral_date": ClinicalEntity[str](value=ref_date, raw_text=ref_date, bbox=ref_date_box, confidence=1.0, status="AUTO_ACCEPTED"),
                "urgency": ClinicalEntity[str](value=record["urgency"], raw_text=record["urgency"], bbox=urgency_box, confidence=1.0, status="AUTO_ACCEPTED"),
                "patient.first_name": ClinicalEntity[str](value=first_name, raw_text=first_name, bbox=fn_box, confidence=1.0, status="AUTO_ACCEPTED"),
                "patient.last_name": ClinicalEntity[str](value=last_name, raw_text=last_name, bbox=ln_box, confidence=1.0, status="AUTO_ACCEPTED"),
                "patient.dob": ClinicalEntity[str](value=dob, raw_text=dob, bbox=dob_box, confidence=1.0, status="AUTO_ACCEPTED"),
                "insurance.member_id": ClinicalEntity[str](value=member_id, raw_text=member_id, bbox=mem_box, confidence=1.0, status="AUTO_ACCEPTED"),
                "insurance.payer_name": ClinicalEntity[str](value=payer, raw_text=payer, bbox=payer_box, confidence=1.0, status="AUTO_ACCEPTED"),
                "referring_provider.name": ClinicalEntity[str](value=prov_name, raw_text=prov_name, bbox=prov_box, confidence=1.0, status="AUTO_ACCEPTED"),
                "referring_provider.npi": ClinicalEntity[str](value=npi, raw_text=npi, bbox=npi_box, confidence=1.0, status="AUTO_ACCEPTED"),
                "diagnosis.icd10_code": ClinicalEntity[str](value=icd10, raw_text=icd10, bbox=icd_box, confidence=1.0, status="AUTO_ACCEPTED"),
                "diagnosis.description": ClinicalEntity[str](value=diag_desc, raw_text=diag_desc, bbox=desc_box, confidence=1.0, status="AUTO_ACCEPTED"),
                "service_requested": ClinicalEntity[str](value=svc["service_type"], raw_text=svc["service_type"], bbox=svc_box, confidence=1.0, status="AUTO_ACCEPTED"),
                "requested_service_date": ClinicalEntity[str](value=svc["requested_date"], raw_text=svc["requested_date"], bbox=svc_date_box, confidence=1.0, status="AUTO_ACCEPTED"),
            },
            routing_decision="AUTO_ACCEPTED",
            overall_confidence=1.0,
            validation_flags=[],
        )

        return img, referral_model

    def apply_fax_degradation(
        self,
        image: Image.Image,
        seed: Optional[int] = None,
        severity: float = 0.5,
    ) -> Image.Image:
        """Applies realistic multi-stage analog fax degradation.

        Stages:
        1. Scan skew (-1.2° to +1.2° rotation)
        2. Thermal fax vertical printhead streak artifacts
        3. Salt-and-pepper photocopier noise
        4. Optical blur and high-contrast binarization
        """
        rng = np.random.default_rng(seed)

        # Work in grayscale for authentic fax characteristics
        gray_img = image.convert("L")

        # 1. Rotational Skew
        skew_angle = float(rng.uniform(-1.2 * severity, 1.2 * severity))
        skewed = gray_img.rotate(skew_angle, resample=Image.Resampling.BILINEAR, fillcolor=255)

        arr = np.array(skewed, dtype=np.float32)

        # 2. Thermal Fax Vertical Streak Artifacts (sensor line defects)
        num_streaks = int(rng.integers(1, 4))
        for _ in range(num_streaks):
            x_pos = int(rng.integers(50, self.width - 50))
            streak_intensity = rng.uniform(0.70, 0.90)  # darkening
            streak_width = int(rng.integers(1, 3))
            arr[:, max(0, x_pos - streak_width) : min(self.width, x_pos + streak_width)] *= streak_intensity

        # 3. Salt-and-Pepper Noise
        noise_prob = 0.008 * severity
        rand_matrix = rng.random(arr.shape)
        # Black speckles on whitespace
        arr[rand_matrix < noise_prob] = 0
        # White dropouts on text
        arr[rand_matrix > (1.0 - (noise_prob * 0.4))] = 255

        # 4. Optical Blur (slight lens softening)
        degraded = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))
        if severity > 0.2:
            degraded = degraded.filter(ImageFilter.GaussianBlur(radius=0.6 * severity))

        # 5. Fax Binarization / Contrast Compression
        # Analog faxes compress via 1-bit run-length encoding (CCITT Group 3/4)
        bin_arr = np.array(degraded, dtype=np.uint8)
        threshold = int(rng.integers(175, 195))
        binarized = np.where(bin_arr < threshold, 0, 255).astype(np.uint8)

        final_fax = Image.fromarray(binarized, mode="L").convert("RGB")
        return final_fax

    def generate_sample_suite(
        self,
        fixtures_file: Path | str,
        output_dir: Path | str,
        degrade: bool = True,
    ) -> List[Tuple[Path, Path, ReferralV1]]:
        """Generates rendered fax images and ground truth JSON files from fixture list."""
        out_path = Path(output_dir)
        out_path.mkdir(parents=True, exist_ok=True)

        with open(fixtures_file, "r", encoding="utf-8") as f:
            fixtures = json.load(f)

        generated = []
        for i, record in enumerate(fixtures):
            img, referral_model = self.render_referral(record)
            if degrade:
                img = self.apply_fax_degradation(img, seed=100 + i, severity=0.6)

            ref_id = record["referral_id"].replace("-", "_").lower()
            img_file = out_path / f"{ref_id}.png"
            json_file = out_path / f"{ref_id}_ground_truth.json"

            img.save(img_file, format="PNG")
            with open(json_file, "w", encoding="utf-8") as f:
                f.write(referral_model.model_dump_json(indent=2))

            generated.append((img_file, json_file, referral_model))

        return generated
