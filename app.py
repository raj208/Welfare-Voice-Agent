import gradio as gr
from speech import transcribe_audio, tts_to_file
from agent_core import process_turn

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

def pairs_to_messages(pairs):
    msgs = []
    for u, a in pairs:
        msgs.append({"role": "user", "content": u})
        msgs.append({"role": "assistant", "content": a})
    return msgs

def voice_turn(audio_file, lang_key, chat_pairs, agent_mem):
    # If mic is empty/cleared, do nothing (prevents crashes)
    if not audio_file:
        return pairs_to_messages(chat_pairs), None, "", "", chat_pairs, agent_mem

    lang_code, lang_name = LANGS[lang_key]

    # 1) STT
    user_text = transcribe_audio(audio_file, lang_code)
    if not user_text:
        bot_text = "मैं आपकी आवाज़ ठीक से नहीं सुन पाया। कृपया फिर से बोलिए।"
        audio_out = tts_to_file(bot_text, "hi")
        return pairs_to_messages(chat_pairs), audio_out, user_text, bot_text, chat_pairs, agent_mem

    # 2) AGENT
    bot_text, agent_mem = process_turn(user_text, lang_name, agent_mem)

    # 3) TTS
    audio_out = tts_to_file(bot_text, lang_code)

    chat_pairs = chat_pairs + [(user_text, bot_text)]
    return pairs_to_messages(chat_pairs), audio_out, user_text, bot_text, chat_pairs, agent_mem


with gr.Blocks(title="Voice Welfare Agent - Step 2") as demo:
    gr.Markdown("## Step 2: Agent + Memory (Voice → STT → Agent → TTS)\nRecord, then click **Send / Process**.")

    lang_key = gr.Dropdown(choices=list(LANGS.keys()), value="Hindi (hi)", label="Language")
    chat = gr.Chatbot(label="Conversation")

    audio_in = gr.Audio(sources=["microphone"], type="filepath", label="Speak (mic)")
    audio_out = gr.Audio(label="Assistant Voice Output", autoplay=True)

    dbg_user = gr.Textbox(label="STT Text (debug)", interactive=False)
    dbg_bot = gr.Textbox(label="Assistant Text (debug)", interactive=False)

    state = gr.State([])  # list of (user, bot)
    agent_state = gr.State({"stage": "INTAKE", "profile": {}, "pending_confirm": None})

    send_btn = gr.Button("Send / Process")

    # ✅ ONLY ONE trigger (button). No audio_in.change at all.
    send_btn.click(
        fn=voice_turn,
        inputs=[audio_in, lang_key, state, agent_state],
        outputs=[chat, audio_out, dbg_user, dbg_bot, state, agent_state],
    ).then(lambda: None, outputs=audio_in)  # clear mic so record button reappears




#REMOVE SEND BUTTON COMPLETELY

# with gr.Blocks(title="Voice Welfare Agent - Step 2") as demo:
#     gr.Markdown("## Step 2: Agent + Memory (Auto)\nRecord your voice — it will process automatically and speak back.")

#     lang_key = gr.Dropdown(choices=list(LANGS.keys()), value="Hindi (hi)", label="Language")
#     chat = gr.Chatbot(label="Conversation")

#     audio_in = gr.Audio(sources=["microphone"], type="filepath", label="Speak (mic)")
#     audio_out = gr.Audio(label="Assistant Voice Output", autoplay=True)

#     dbg_user = gr.Textbox(label="STT Text (debug)", interactive=False)
#     dbg_bot = gr.Textbox(label="Assistant Text (debug)", interactive=False)

#     state = gr.State([])  # list of (user, bot) pairs
#     agent_state = gr.State({"stage": "INTAKE", "profile": {}, "pending_confirm": None})

#     # ✅ NEW: to prevent double-trigger on same recording
#     last_audio = gr.State("")

#     def voice_turn(audio_file, lang_key, chat_pairs, agent_mem, last_audio_path):
#         # ignore clears
#         if not audio_file:
#             return pairs_to_messages(chat_pairs), None, "", "", chat_pairs, agent_mem, last_audio_path

#         # ✅ dedupe: Gradio sometimes fires change twice with same file path
#         if audio_file == last_audio_path:
#             return pairs_to_messages(chat_pairs), None, "", "", chat_pairs, agent_mem, last_audio_path

#         last_audio_path = audio_file  # mark as processed
#         lang_code, lang_name = LANGS[lang_key]

#         user_text = transcribe_audio(audio_file, lang_code)
#         if not user_text:
#             bot_text = "मैं आपकी आवाज़ ठीक से नहीं सुन पाया। कृपया फिर से बोलिए।"
#             audio_reply = tts_to_file(bot_text, "hi")
#             return pairs_to_messages(chat_pairs), audio_reply, user_text, bot_text, chat_pairs, agent_mem, last_audio_path

#         bot_text, agent_mem = process_turn(user_text, lang_name, agent_mem)
#         audio_reply = tts_to_file(bot_text, lang_code)

#         chat_pairs = chat_pairs + [(user_text, bot_text)]
#         return pairs_to_messages(chat_pairs), audio_reply, user_text, bot_text, chat_pairs, agent_mem, last_audio_path

#     evt = audio_in.change(
#         fn=voice_turn,
#         inputs=[audio_in, lang_key, state, agent_state, last_audio],
#         outputs=[chat, audio_out, dbg_user, dbg_bot, state, agent_state, last_audio],
#     )

#     # ✅ clear mic after processing so record button comes back
#     evt.then(lambda: None, outputs=audio_in)



demo.launch()
