"""Enterprise Configuration & Environment Management for Intake AI.

Loads environment variables from .env with production defaults, supporting
pluggable OCR backends (Native, Tesseract, AWS Textract) and Multimodal LLMs
(Google Gemini, OpenAI GPT-4o, Anthropic Claude, Local Ollama).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field


def _load_dotenv_if_present(dotenv_path: Optional[Path] = None) -> None:
    """Lightweight zero-dependency .env parser."""
    if dotenv_path is None:
        dotenv_path = Path(__file__).parent.parent / ".env"

    if not dotenv_path.exists():
        return

    try:
        with open(dotenv_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k = k.strip()
                v = v.strip().strip("'\"")
                if k and k not in os.environ:
                    os.environ[k] = v
    except Exception:
        pass


# Load .env on import
_load_dotenv_if_present()


class IntakeSettings(BaseModel):
    """Production configuration schema for Intake AI."""

    # Server & Runtime
    host: str = Field(default_factory=lambda: os.getenv("HOST", "127.0.0.1"))
    port: int = Field(default_factory=lambda: int(os.getenv("PORT", "8001")))
    debug: bool = Field(default_factory=lambda: os.getenv("DEBUG", "false").lower() == "true")
    environment: str = Field(default_factory=lambda: os.getenv("ENVIRONMENT", "production"))

    # OCR Engine Selection
    # "auto": tries Native Windows OCR -> Heuristic/Tesseract
    # "native": Windows Hardware-Accelerated OCR
    # "tesseract": Local Tesseract CLI
    # "multimodal_llm": Direct Vision LLM zero-shot extraction
    ocr_backend: str = Field(default_factory=lambda: os.getenv("OCR_BACKEND", "auto").lower())

    # Multimodal Vision LLM Settings
    # "none", "gemini", "openai", "anthropic", "ollama"
    llm_provider: str = Field(default_factory=lambda: os.getenv("LLM_PROVIDER", "none").lower())
    gemini_api_key: Optional[str] = Field(default_factory=lambda: os.getenv("GEMINI_API_KEY"))
    gemini_model: str = Field(default_factory=lambda: os.getenv("GEMINI_MODEL", "gemini-2.5-flash"))
    openai_api_key: Optional[str] = Field(default_factory=lambda: os.getenv("OPENAI_API_KEY"))
    openai_model: str = Field(default_factory=lambda: os.getenv("OPENAI_MODEL", "gpt-4o-mini"))
    anthropic_api_key: Optional[str] = Field(default_factory=lambda: os.getenv("ANTHROPIC_API_KEY"))
    anthropic_model: str = Field(default_factory=lambda: os.getenv("ANTHROPIC_MODEL", "claude-3-5-sonnet-20241022"))
    ollama_base_url: str = Field(default_factory=lambda: os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"))
    ollama_model: str = Field(default_factory=lambda: os.getenv("OLLAMA_MODEL", "llama3.2-vision"))

    # Conformal Risk Router Thresholds
    conformal_alpha: float = Field(default_factory=lambda: float(os.getenv("CONFORMAL_ALPHA", "0.05")))
    min_overall_confidence: float = Field(default_factory=lambda: float(os.getenv("MIN_OVERALL_CONFIDENCE", "0.85")))
    min_critical_confidence: float = Field(default_factory=lambda: float(os.getenv("MIN_CRITICAL_CONFIDENCE", "0.88")))

    # HL7 FHIR & EHR Integration
    ehr_fhir_endpoint: Optional[str] = Field(default_factory=lambda: os.getenv("EHR_FHIR_ENDPOINT"))
    webhook_on_approval: Optional[str] = Field(default_factory=lambda: os.getenv("WEBHOOK_ON_APPROVAL"))
    hipaa_audit_log_enabled: bool = Field(default_factory=lambda: os.getenv("HIPAA_AUDIT_LOG_ENABLED", "true").lower() == "true")

    def get_active_llm_status(self) -> Dict[str, Any]:
        """Returns metadata about which LLM or OCR engine is active."""
        if self.llm_provider == "gemini" and self.gemini_api_key:
            return {"active": True, "provider": "gemini", "model": self.gemini_model}
        elif self.llm_provider == "openai" and self.openai_api_key:
            return {"active": True, "provider": "openai", "model": self.openai_model}
        elif self.llm_provider == "anthropic" and self.anthropic_api_key:
            return {"active": True, "provider": "anthropic", "model": self.anthropic_model}
        elif self.llm_provider == "ollama":
            return {"active": True, "provider": "ollama", "model": self.ollama_model}
        return {"active": False, "provider": "deterministic_ocr", "model": self.ocr_backend}


settings = IntakeSettings()
