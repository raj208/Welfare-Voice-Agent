# Voice Welfare Agent (Hindi) 🇮🇳

**A Voice-First, Agentic AI Assistant for Government Welfare Schemes**

[![Language](https://img.shields.io/badge/Language-Hindi-orange)](https://github.com/)
[![Tech Stack](https://img.shields.io/badge/Stack-Gradio%20|%20Faster--Whisper%20|%20Python-blue)](https://github.com/)
[![Status](https://img.shields.io/badge/Status-Prototype-green)](https://github.com/)

## 📖 Overview

[cite_start]The **Voice Welfare Agent** is a voice-first AI system designed to help users find and apply for government welfare schemes entirely through a native Indian language (Hindi)[cite: 3].

Unlike simple chatbots, this system operates as an **autonomous agent** with a deterministic state machine. It listens to user queries, manages conversation memory across turns, actively detects contradictions in user inputs, and utilizes external tools to retrieve schemes, check eligibility rules, and simulate application submissions.

---

## ✨ What this project does

**End-to-end pipeline:**
1. **Voice Input (Mic)** → Gradio UI
2. **STT (Speech-to-Text)** → `faster-whisper` transcribes Hindi audio
3. **Normalize + Canonicalize** → fixes common STT variations (Hindi)
4. **Agent Core (State Machine + Memory)** → decides next step
5. **Tools**
   - `search_schemes()` → retrieve top schemes
   - `check_eligibility()` → evaluate eligibility rules
   - `save_application()` → generate tracking ID
6. **TTS (Text-to-Speech)** → `gTTS` generates Hindi audio reply
7. **UI Output** → Chat + audio + debug trace

---

## ✅ Implemented Features 

### Voice + Multilingual UI
- Mic recording input via Gradio
- Hindi conversation end-to-end (STT → Agent → TTS)
- Dropdown for language selection (Hindi is the primary demo)

### Explicit Agent Lifecycle (State Machine)
Stages used:
- `INTAKE`
- `PROFILE_COLLECTION`
- `READY`
- `RECOMMEND`
- `CONFIRM_SUBMIT`
- `DONE`

### Memory Across Turns
Agent memory persists during session using `gr.State`, including:
- `stage`, `goal`, `profile`, `expected_field`
- `pending_confirm` (contradiction resolver)
- `last_results`, `selected_scheme`
- `last_trace` (Tool/State Trace for demo/debug)

### Contradiction Handling
If user changes a known value (e.g., age 20 → 21), agent asks:
- “क्या मैं अपडेट कर दूँ? (हाँ/नहीं)”
- YES → update profile
- NO → keep old value

### Tools (3 total)
- **Retriever tool:** `search_schemes(query, top_k=3)`
- **Eligibility tool:** `check_eligibility(scheme_id, profile)`
- **Submit tool:** `save_application(profile, scheme)` → returns `tracking_id`

### Failure Handling
- Empty audio / cleared mic → safely ignored
- STT returns empty text → asks user to speak again
- Unparseable answers for expected field → re-asks the same question
- Missing fields for eligibility → asks missing field before final recommendation

### Tool/State Trace (Debug)
UI shows a trace like:
- `stage=READY → tool=retriever(...) → tool=eligibility(...) → stage=RECOMMEND`

---

## 🧠 Agent Behavior Summary

### Profile collection (minimal required fields)
By default, the agent collects:
- `state`
- `age`
- `annual_income`
- `category` (SC/ST/OBC/General/EWS)

It may also ask **only when needed by eligibility rules**:
- `gender` (male/female)
- `is_student` (हाँ/नहीं)

### Recommendation flow
- Retrieves top 3 schemes
- Evaluates eligibility per scheme:
  - ✅ eligible
  - ❌ not eligible
  - ⚠️ unknown / missing info
- User selects scheme (1/2/3) → sees apply steps + documents
- User confirms submit (हाँ/नहीं) → tracking id is generated

---


## 🚀 Installation & Setup

### Prerequisites
* Python 3.9+
* [cite_start]FFmpeg (required for audio processing via faster-whisper) [cite: 91]

### 1. Clone the repository
```bash```
git clone [https://github.com/raj208/voice-welfare-agent.git](https://github.com/raj208/voice-welfare-agent.git)
cd voice-welfare-agent


### 2. Create a Virtual Environment

#### Windows
```bash```
python -m venv .venv
.venv\Scripts\activate

#### macOS/Linux
```bash```
python3 -m venv .venv
source .venv/bin/activate



### 3. Install Dependencies
```bash```
pip install -r requirements.txt


### 4. Run the Application
```bash```
python app.py
