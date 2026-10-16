import tempfile
from pathlib import Path
from typing import List
import ollama
import streamlit as st
from analyzer import RecruiterVoiceAnalyzer, MAX_FILE_SIZE_BYTES

st.set_page_config(
    page_title="Student Recruiter Voice Guard",
    page_icon="🛡️",
    layout="centered",
)


def get_installed_ollama_models() -> List[str]:
    """Fetches locally available Ollama models, falling back to defaults if unavailable."""
    try:
        models_info = ollama.list()
        models = getattr(models_info, "models", None) or models_info.get("models", [])
        names = [
            getattr(m, "model", None) or m.get("model") or m.get("name")
            for m in models
        ]
        names = [n for n in names if n]
        return names if names else ["llama3.2", "qwen3:8b", "mistral"]
    except Exception:
        return ["llama3.2", "qwen3:8b", "mistral"]


# Sidebar Configuration
with st.sidebar:
    st.header("⚙️ Model Settings")
    available_models = get_installed_ollama_models()
    selected_ollama_model = st.selectbox(
        "Local Ollama LLM",
        options=available_models,
        help="Select the local Ollama model used to analyze recruitment scam language.",
    )
    selected_whisper_model = st.selectbox(
        "Whisper Transcription Model",
        options=["base", "small", "tiny", "medium"],
        index=0,
    )
    st.caption(
        "Deepfake audio detection is powered by the Detectif.ai REST API (`/v1/deepfake/detect`)."
    )

st.title("🛡️ Recruiter Voice Note Scam & Deepfake Detector")
st.write(
    "Upload an internship or job recruitment voice note to analyze it for **AI-cloned speech** "
    "(via Detectif.ai) and **recruitment scam tactics** (via your local Ollama LLM)."
)

uploaded_file = st.file_uploader(
    "Upload Recruiter Audio Recording (Max 100 MB)",
    type=["wav", "mp3", "m4a", "ogg", "flac"],
)

if uploaded_file is not None:
    st.audio(uploaded_file)

    if uploaded_file.size > MAX_FILE_SIZE_BYTES:
        st.error("File exceeds the 100 MB upload limit. Please upload a smaller recording.")
    elif st.button("Analyze Voice Note", type="primary"):
        with st.spinner(
            f"Running Detectif.ai deepfake detection and analyzing transcript with Ollama ({selected_ollama_model})..."
        ):
            suffix = Path(uploaded_file.name).suffix or ".wav"
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp_file:
                tmp_file.write(uploaded_file.read())
                tmp_path = tmp_file.name

            try:
                analyzer = RecruiterVoiceAnalyzer(
                    whisper_model_size=selected_whisper_model,
                    ollama_model=selected_ollama_model,
                )
                result = analyzer.evaluate_voice_note(tmp_path)

                # Risk Level Banner
                badge_colors = {
                    "LOW": "green",
                    "MEDIUM": "orange",
                    "HIGH": "red",
                    "CRITICAL": "red",
                }
                color = badge_colors.get(result.risk_level, "gray")
                st.markdown(
                    f"### Risk Assessment: :{color}[**{result.risk_level} RISK**] "
                    f"(Score: {result.overall_risk_score}/100)"
                )

                # Top-Level Metrics
                col1, col2, col3 = st.columns(3)
                col1.metric(
                    "AI / Deepfake Probability",
                    f"{result.deepfake_probability * 100:.1f}%",
                )
                col2.metric(
                    "Voice Verdict",
                    "Synthetic / Manipulated" if result.is_synthetic_voice else "Likely Authentic",
                )
                col3.metric("Scam Flags Identified", len(result.scam_flags))

                # Recruiter Intent & Transcript
                st.subheader("🎯 Caller Intent Summary")
                st.write(result.intent_summary)

                st.subheader("📝 Voice Note Transcript")
                st.info(result.transcript or "No intelligible speech detected.")

                # Ollama Scam Language Flags
                st.subheader("🚩 Scam & Manipulation Indicators (Ollama Analysis)")
                if not result.scam_flags:
                    st.success("No recruitment scam language or manipulation tactics detected.")
                else:
                    for flag in result.scam_flags:
                        st.warning(
                            f"**{flag.category}** (Severity: {flag.severity}/10)\n\n"
                            f"**Matched Quote:** *\"{flag.matched_phrase}\"*\n\n"
                            f"{flag.explanation}"
                        )

                # Student Safety Recommendations
                st.subheader("✅ Student Safety Recommendations")
                for rec in result.recommendations:
                    st.markdown(f"- {rec}")

                with st.expander("View Raw Detectif.ai API Response"):
                    st.json(result.raw_api_response)

            except Exception as e:
                st.error(f"Analysis failed: {e}")
            finally:
                Path(tmp_path).unlink(missing_ok=True)