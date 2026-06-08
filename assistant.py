import os
import json
import datetime
from dotenv import load_dotenv
from audio_utils import listen_for_wake_word, record_audio, play_audio
from api_clients import setup_gemini, get_gemini_response, sarvam_stt, sarvam_tts

load_dotenv()
setup_gemini()

LANGUAGE_MAP = {
    "en-IN": "en-IN",
    "hi-IN": "hi-IN",
    "kn-IN": "kn-IN",
    "ta-IN": "ta-IN",
    "te-IN": "te-IN",
    "ml-IN": "ml-IN",
    "mr-IN": "mr-IN",
    "bn-IN": "bn-IN",
    "gu-IN": "gu-IN",
    "pa-IN": "pa-IN",
    "or-IN": "or-IN"
}

def load_knowledge_base():
    try:
        with open("knowledge_base.json", "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def log_conversation(role, text):
    os.makedirs("logs", exist_ok=True)
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    with open(f"logs/{today}.txt", "a", encoding="utf-8") as f:
        f.write(f"{role}: {text}\n")

def run_assistant():
    print("=======================================")
    print(" Starting Advanced Voice Assistant...  ")
    print("=======================================")
    
    kb = load_knowledge_base()
    chat_history = []
    
    while True:
        # Wait for wake word using speech_recognition
        success = listen_for_wake_word("hello")
        if not success:
            print("Wake word detection failed. Exiting.")
            break
            
        # Record user query
        audio_file = record_audio("input.wav", duration=6)
        if not audio_file:
            continue
            
        # STT via Sarvam
        print("Transcribing with Sarvam STT...")
        transcript, lang_code = sarvam_stt(audio_file)
        if not transcript:
            print("Could not understand audio. Try again.")
            continue
            
        print(f"\nUser: {transcript} (Detected Lang: {lang_code})")
        log_conversation("User", transcript)
        
        # Check exit commands
        lower_transcript = transcript.lower().strip()
        if any(cmd in lower_transcript for cmd in ["stop", "exit", "goodbye"]):
            print("Exiting assistant...")
            sarvam_tts("Goodbye!", "en-IN", "output.wav")
            play_audio("output.wav")
            break
            
        # Map Language for TTS safety
        mapped_lang = LANGUAGE_MAP.get(lang_code, "en-IN")
            
        # Get response from Gemini
        print("Thinking (Gemini 2.5 Flash)...")
        answer = get_gemini_response(transcript, chat_history, mapped_lang, kb)
        print(f"Assistant: {answer}\n")
        log_conversation("Assistant", answer)
        
        # Update history
        chat_history.append({"role": "user", "content": transcript})
        chat_history.append({"role": "assistant", "content": answer})
        
        # TTS via Sarvam
        print("Generating audio with Sarvam TTS...")
        if sarvam_tts(answer, mapped_lang, "output.wav"):
            play_audio("output.wav")
        else:
            print("Failed to generate audio response.")

if __name__ == "__main__":
    run_assistant()
