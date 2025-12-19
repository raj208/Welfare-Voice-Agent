import os
import tempfile
from gtts import gTTS
from faster_whisper import WhisperModel

# Load once (CPU works; GPU optional later)
_MODEL_SIZE = os.getenv("WHISPER_MODEL", "small")
_whisper = WhisperModel(_MODEL_SIZE, device="cpu", compute_type="int8")

def transcribe_audio(audio_path: str, language_code: str) -> str:
    if not audio_path:        # ✅ handles None / empty
        return ""

    segments, info = _whisper.transcribe(
        audio_path,
        language=language_code,
        vad_filter=True
    )
    text = " ".join([seg.text.strip() for seg in segments]).strip()
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
