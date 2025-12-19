import gradio as gr
from speech import transcribe_audio, tts_to_file
from llm_backends import generate_reply

LANGS = {
    "Hindi (hi)": ("hi", "Hindi"),
    "Bengali (bn)": ("bn", "Bengali"),
    "Tamil (ta)": ("ta", "Tamil"),
    "Telugu (te)": ("te", "Telugu"),
    "Marathi (mr)": ("mr", "Marathi"),
    "Odia (or)": ("or", "Odia"),
    "Gujarati (gu)": ("gu", "Gujarati"),
    "Kannada (kn)": ("kn", "Kannada"),
    "Malayalam (ml)": ("ml", "Malayalam"),
    "Punjabi (pa)": ("pa", "Punjabi"),
}
# ... keep your imports + LANGS + voice_turn signature above ...



def pairs_to_messages(pairs):
    msgs = []
    for u, a in pairs:
        msgs.append({"role": "user", "content": u})
        msgs.append({"role": "assistant", "content": a})
    return msgs

# [
#   {"role": "user", "content": "..." },
#   {"role": "assistant", "content": "..." }
# ]


def voice_turn(audio_file, lang_key, chat_pairs):
    lang_code, lang_name = LANGS[lang_key]

    # 1) STT
    user_text = transcribe_audio(audio_file, lang_code)
    if not user_text:
        bot_text = "मैं आपकी आवाज़ ठीक से नहीं सुन पाया। कृपया फिर से बोलिए।"  # change to your language later
        audio_out = tts_to_file(bot_text, "hi")
        return pairs_to_messages(chat_pairs), audio_out, user_text, bot_text, chat_pairs

    # 2) LLM (uses pairs history)
    bot_text = generate_reply(user_text, chat_pairs, lang_name)

    # 3) TTS
    audio_out = tts_to_file(bot_text, lang_code)

    chat_pairs = chat_pairs + [(user_text, bot_text)]
    return pairs_to_messages(chat_pairs), audio_out, user_text, bot_text, chat_pairs


with gr.Blocks(title="Voice Welfare Agent - Step 1") as demo:
    gr.Markdown("## Step 1: Voice → STT → LLM → TTS (Non-English)\nSpeak in your chosen language.")

    lang_key = gr.Dropdown(choices=list(LANGS.keys()), value="Hindi (hi)", label="Language")

    # IMPORTANT: explicitly use messages format
    # chat = gr.Chatbot(label="Conversation", type="messages")
    chat = gr.Chatbot(label="Conversation")


    audio_in = gr.Audio(sources=["microphone"], type="filepath", label="Speak (mic)")
    audio_out = gr.Audio(label="Assistant Voice Output", autoplay=True)

    dbg_user = gr.Textbox(label="STT Text (debug)", interactive=False)
    dbg_bot = gr.Textbox(label="LLM Reply (debug)", interactive=False)

    state = gr.State([])  # stores list of (user, bot) pairs

    audio_in.change(
        fn=voice_turn,
        inputs=[audio_in, lang_key, state],
        outputs=[chat, audio_out, dbg_user, dbg_bot, state],
    )

demo.launch()
