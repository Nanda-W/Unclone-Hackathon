# 🛡️ Student Recruiter Voice Guard

**Student Recruiter Voice Guard** is an AI-powered security tool designed to help university students identify suspicious internship and job recruitment voice notes before trusting a recruiter. Users can upload an audio recording to analyze it for signs of AI-generated or manipulated speech alongside recruitment scam language, receiving a clear risk assessment and actionable safety recommendations.

---

## ✨ Key Features

* **Audio Deepfake Detection**: Integrates with the Detectif.ai REST API (`https://platform.detectif.ai/v1/deepfake/detect`) to evaluate uploaded recordings for synthetic or cloned voices.
* **Reliable Multipart Uploads**: Supports audio uploads via multipart `file` requests up to 100 MB.
* **Idempotent API Retries**: Sends an `Idempotency-Key` header on model operations and reuses it across network retries to prevent duplicate processing.
* **Local Speech-to-Text Transcription**: Uses OpenAI Whisper locally to transcribe recruitment voice notes into text without exposing student audio to additional third-party transcription clouds.
* **Context-Aware Scam Analysis (Ollama)**: Uses a local Ollama LLM (such as `llama3.2` or `qwen3`) with structured Pydantic JSON outputs to detect upfront fee requests, no-interview job offers, urgency tactics, and banking/OTP phishing.
* **Student Risk Scoring & Safety Playbook**: Combines the synthetic voice probability and linguistic scam indicators into a `LOW`, `MEDIUM`, `HIGH`, or `CRITICAL` rating with tailored verification steps.

---

## 🏗️ System Architecture

```text
[ Uploaded Audio Recording (WAV / MP3 / M4A / OGG / FLAC, up to 100 MB) ]
         │
         ├──► 1. Detectif.ai REST API (/v1/deepfake/detect)
         │       └─► Returns Synthetic / Deepfake Voice Probability
         │
         └──► 2. Local OpenAI Whisper Model
                 └─► Generates Voice Note Transcript
                         │
                         ▼
              3. Local Ollama LLM (Structured JSON Output)
                 └─► Analyzes Transcript + Deepfake Score for Scam Flags
                         │
                         ▼
              4. Streamlit Student Dashboard
                 └─► Displays Risk Level, Matched Quotes & Safety Steps
```

---

## 📂 Project Structure

```text
├── analyzer.py           # Core pipeline: Detectif.ai API client, Whisper STT, and Ollama analyzer
├── app.py                # Streamlit web interface for students
├── ollama_mcp_agent.py   # (Optional) Script connecting Ollama to the DetectifAI MCP server
└── README.md             # Project documentation
```

---

## 🚀 Getting Started

### 1. Prerequisites

* **Python 3.9+**
* **FFmpeg**: Required by OpenAI Whisper for audio decoding.
  * **Windows (PowerShell)**:
    ```powershell
    winget install --id=Gyan.FFmpeg -e
    ```
  * **macOS (Homebrew)**:
    ```bash
    brew install ffmpeg
    ```
  * **Ubuntu / Debian**:
    ```bash
    sudo apt update && sudo apt install ffmpeg -y
    ```
* **Ollama**: Download and start [Ollama](https://ollama.com/), then pull a local model:
  ```bash
  ollama pull llama3.2
  ```
* **Detectif.ai API Key**: Create an API key (`dtf_live_...`) on your Detectif.ai dashboard.

### 2. Install Python Dependencies

```bash
pip install requests openai-whisper ollama pydantic streamlit
```

### 3. Configure Your API Key

Keep your API key in the `DETECTIF_API_KEY` environment variable and never place it in a URL.

* **Windows (PowerShell)**:
  ```powershell
  $env:DETECTIF_API_KEY="dtf_live_your_api_key_here"
  ```
* **Windows (Command Prompt)**:
  ```cmd
  set DETECTIF_API_KEY=dtf_live_your_api_key_here
  ```
* **macOS / Linux (Bash / Zsh)**:
  ```bash
  export DETECTIF_API_KEY="dtf_live_your_api_key_here"
  ```

### 4. Run the Application

```bash
streamlit run app.py
```

Open your browser to `http://localhost:8501` to upload a recruitment voice note and view the risk assessment.

---

## 🔌 Optional: DetectifAI MCP Server Integration

DetectifAI also runs a Model Context Protocol (MCP) server so AI assistants and MCP clients (such as Claude Code, Cursor, VS Code, Codex, Windsurf, Claude Desktop, or custom Python agents) can check recordings and manage enrolled speakers.

* **Server URL**: `https://platform.detectif.ai/mcp`
* **Transport**: `Streamable HTTP`
* **Authentication Header**: `Authorization: Bearer <your API key>`

To run the standalone Ollama + MCP agent:

```bash
pip install mcp ollama
python ollama_mcp_agent.py
```

---

## 🛡️ Security & Privacy Best Practices

* **Credential Hygiene**: Always pass your Detectif.ai key via the `Authorization: Bearer` request header from an environment variable, and never hardcode keys into source files or URLs.
* **Temporary File Cleanup**: Uploaded audio files are processed in temporary storage and automatically deleted (`unlink`) immediately after analysis completes.
* **Advisory Use**: This tool provides automated risk indicators to assist students and university career cells; students should always verify recruiters independently through official corporate domains and campus placement offices.