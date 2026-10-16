import os
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Any, Optional
import requests
import whisper
import ollama
from pydantic import BaseModel, Field

# Detectif.ai REST API Configuration
DETECTIF_BASE_URL = "https://platform.detectif.ai/v1"
DEEPFAKE_ENDPOINT = f"{DETECTIF_BASE_URL}/deepfake/detect"
MAX_FILE_SIZE_BYTES = 100 * 1024 * 1024  # 100 MB limit per API specification


# Pydantic Schemas for Ollama Structured Output
class ScamFlag(BaseModel):
    category: str = Field(
        description="Short category name, e.g., 'Upfront Fee Request', 'No-Interview Offer', 'Urgency Manipulation', 'Financial/OTP Request', or 'Off-Platform Task Scam'."
    )
    severity: int = Field(
        ge=1,
        le=10,
        description="Severity score from 1 (minor concern) to 10 (critical scam indicator).",
    )
    matched_phrase: str = Field(
        description="Exact quote or phrase from the transcript that triggered this flag."
    )
    explanation: str = Field(
        description="Clear explanation of why this phrase is suspicious for a student job/internship applicant."
    )


class LLMScamAssessment(BaseModel):
    intent_summary: str = Field(
        description="A 1-2 sentence summary of what the recruiter is asking the student to do."
    )
    llm_risk_score: float = Field(
        ge=0.0,
        le=100.0,
        description="Risk score (0-100) based on the language, manipulation tactics, and synthetic voice probability.",
    )
    scam_flags: List[ScamFlag] = Field(
        default_factory=list,
        description="List of specific scam indicators found in the transcript. Empty if completely benign.",
    )
    recommendations: List[str] = Field(
        description="3 to 5 actionable safety steps tailored to the student based on this voice note."
    )


@dataclass
class AssessmentResult:
    risk_level: str  # LOW, MEDIUM, HIGH, CRITICAL
    overall_risk_score: float  # 0.0 to 100.0
    deepfake_probability: float  # 0.0 to 1.0
    is_synthetic_voice: bool
    transcript: str
    intent_summary: str
    scam_flags: List[ScamFlag] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)
    raw_api_response: Dict[str, Any] = field(default_factory=dict)


class RecruiterVoiceAnalyzer:
    def __init__(
        self,
        api_key: Optional[str] = None,
        whisper_model_size: str = "base",
        ollama_model: str = "llama3.2",
    ):
        self.api_key = api_key or os.environ.get("DETECTIF_API_KEY")
        if not self.api_key:
            raise ValueError(
                "Missing API key. Set the DETECTIF_API_KEY environment variable."
            )
        self.ollama_model = ollama_model
        self.whisper_model = whisper.load_model(whisper_model_size)

    def detect_deepfake(
        self, file_path: str, max_retries: int = 3, timeout: int = 30
    ) -> Dict[str, Any]:
        """
        Uploads audio to Detectif.ai /v1/deepfake/detect using a persistent Idempotency-Key
        across retries.
        """
        path = Path(file_path)
        if not path.is_file():
            raise FileNotFoundError(f"Audio file not found: {file_path}")

        file_size = path.stat().st_size
        if file_size > MAX_FILE_SIZE_BYTES:
            raise ValueError(
                f"File size ({file_size / (1024 * 1024):.1f} MB) exceeds the 100 MB limit."
            )

        # Create one Idempotency-Key and reuse it across all retry attempts
        idempotency_key = str(uuid.uuid4())
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Idempotency-Key": idempotency_key,
        }

        last_exception = None
        for attempt in range(1, max_retries + 1):
            try:
                with open(path, "rb") as audio_file:
                    files = {"file": (path.name, audio_file)}
                    response = requests.post(
                        DEEPFAKE_ENDPOINT,
                        headers=headers,
                        files=files,
                        timeout=timeout,
                    )

                if response.status_code in (429, 500, 502, 503, 504):
                    time.sleep(2 ** (attempt - 1))
                    continue

                response.raise_for_status()
                return response.json()

            except requests.RequestException as exc:
                last_exception = exc
                if attempt < max_retries:
                    time.sleep(2 ** (attempt - 1))

        raise RuntimeError(
            f"Detectif.ai API request failed after {max_retries} attempts: {last_exception}"
        )

    @staticmethod
    def _extract_synthetic_probability(api_response: Dict[str, Any]) -> float:
        """Normalizes the synthetic probability score (0.0 to 1.0) from Detectif.ai."""
        candidate_keys = [
            "synthetic_probability",
            "synthetic_score",
            "deepfake_probability",
            "probability",
            "score",
            "confidence",
        ]
        search_spaces = [
            api_response,
            api_response.get("data", {}) if isinstance(api_response.get("data"), dict) else {},
            api_response.get("result", {}) if isinstance(api_response.get("result"), dict) else {},
        ]

        for space in search_spaces:
            for key in candidate_keys:
                if key in space and isinstance(space[key], (int, float)):
                    val = float(space[key])
                    return val / 100.0 if val > 1.0 else val

        if api_response.get("is_deepfake") or api_response.get("verdict") == "synthetic":
            return 0.90
        return 0.0

    def transcribe_audio(self, file_path: str) -> str:
        """Transcribes the uploaded voice note to text using Whisper."""
        result = self.whisper_model.transcribe(file_path, fp16=False)
        return result.get("text", "").strip()

    def analyze_with_ollama(
        self, transcript: str, deepfake_prob: float
    ) -> LLMScamAssessment:
        """
        Uses a local Ollama model with structured JSON output to analyze the transcript
        and deepfake probability for student recruitment scam indicators.
        """
        system_prompt = (
            "You are an expert cybersecurity and student career safety analyst. "
            "Your job is to protect university students from fraudulent internship and job recruitment voice notes. "
            "Look closely for: "
            "1) Upfront fees (training, registration, security deposits, laptop/equipment charges). "
            "2) Requests for sensitive financial or identity data (bank details, UPI/crypto, OTPs, government IDs). "
            "3) Unsolicited instant job/internship offers without a real interview. "
            "4) Task scams or unrealistic pay for minimal effort on WhatsApp/Telegram. "
            "5) High-pressure urgency tactics forcing immediate action or payment. "
            "Always return valid JSON matching the requested schema."
        )

        user_prompt = f"""
        Evaluate the following recruitment voice note sent to a student:

        - Detectif.ai Synthetic/Deepfake Voice Probability: {deepfake_prob * 100:.1f}%
        - Voice Note Transcript: "{transcript if transcript else '[No intelligible speech detected]'}"

        Provide a structured scam assessment and actionable safety recommendations for the student.
        """

        response = ollama.chat(
            model=self.ollama_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            format=LLMScamAssessment.model_json_schema(),
            options={"temperature": 0.1},
        )

        return LLMScamAssessment.model_validate_json(response["message"]["content"])

    def evaluate_voice_note(self, file_path: str) -> AssessmentResult:
        """Runs the end-to-end pipeline: Detectif.ai Deepfake Check + Whisper + Ollama Analysis."""
        # 1. Deepfake Detection via Detectif.ai REST API
        api_response = self.detect_deepfake(file_path)
        deepfake_prob = self._extract_synthetic_probability(api_response)
        is_synthetic = deepfake_prob >= 0.50

        # 2. Speech-to-Text Transcription
        transcript = self.transcribe_audio(file_path)

        # 3. Context-Aware Scam Analysis via Local Ollama LLM
        llm_assessment = self.analyze_with_ollama(transcript, deepfake_prob)

        # 4. Combine Deepfake Signal + Ollama Risk Score into Final Risk Assessment
        deepfake_score = deepfake_prob * 100.0
        flag_score = min(sum(flag.severity * 5.0 for flag in llm_assessment.scam_flags), 75.0)
        linguistic_score = max(llm_assessment.llm_risk_score, flag_score)

        # Weight both signals and boost if both voice synthesis and scam language occur together
        synergy_boost = 15.0 if (is_synthetic and llm_assessment.scam_flags) else 0.0
        overall_score = min(
            100.0,
            (deepfake_score * 0.45) + (linguistic_score * 0.55) + synergy_boost,
        )

        # Ensure high deepfake probability or severe scam flags never result in a low rating
        if is_synthetic:
            overall_score = max(overall_score, 60.0)
        if any(f.severity >= 9 for f in llm_assessment.scam_flags):
            overall_score = max(overall_score, 75.0)

        if overall_score >= 75.0:
            risk_level = "CRITICAL"
        elif overall_score >= 50.0:
            risk_level = "HIGH"
        elif overall_score >= 25.0:
            risk_level = "MEDIUM"
        else:
            risk_level = "LOW"

        return AssessmentResult(
            risk_level=risk_level,
            overall_risk_score=round(overall_score, 1),
            deepfake_probability=round(deepfake_prob, 3),
            is_synthetic_voice=is_synthetic,
            transcript=transcript,
            intent_summary=llm_assessment.intent_summary,
            scam_flags=llm_assessment.scam_flags,
            recommendations=llm_assessment.recommendations,
            raw_api_response=api_response,
        )