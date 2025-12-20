import os
import tempfile
from gtts import gTTS
from faster_whisper import WhisperModel

# Load once (CPU works; GPU optional later)
_MODEL_SIZE = os.getenv("WHISPER_MODEL", "medium")
_whisper = WhisperModel(_MODEL_SIZE, device="cpu", compute_type="int8")

def transcribe_audio(audio_path: str, language_code: str) -> str:
    if not audio_path:
        return ""

    segments, info = _whisper.transcribe(
        audio_path,
        language=language_code,
        vad_filter=True,
        beam_size=5,                    # ✅ better decoding
        temperature=0.0,                # ✅ less randomness
        condition_on_previous_text=False,  # ✅ helps short answers
        initial_prompt=(
            "यह सरकारी योजनाओं की बातचीत है। "
            "उम्र, आय, राज्य, श्रेणी (SC/ST/OBC/General/EWS), "
            "और 1/2/3 जैसे विकल्प बोला जा सकता है।"
        ) if language_code == "hi" else None
    )

    text = " ".join(seg.text.strip() for seg in segments).strip()
    return text



def tts_to_file(text: str, language_code: str) -> str:
    """
    Returns a path to an mp3 file.
    gTTS language codes: hi, bn, ta, te, mr, or, gu, kn, ml, pa, ur...
    """
    if not text:
        text = " "

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
    tmp.close()

    tts = gTTS(text=text, lang=language_code)
    tts.save(tmp.name)
    return tmp.name
