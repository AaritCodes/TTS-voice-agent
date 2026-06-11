import os
import requests
import google.generativeai as genai
import json

# Configure Gemini
def setup_gemini():
    genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

def get_gemini_response(prompt_text, chat_history, language_code, kb_context):
    try:
        model = genai.GenerativeModel('gemini-2.5-flash')
        
        system_prompt = f"""You are a helpful multilingual voice assistant.
Rules:
1. Answer concisely and naturally for voice conversations. Keep your reply extremely short (1-2 sentences, maximum 300 characters).
2. CRITICAL: Your response MUST be under 400 characters to fit TTS engine constraints.
3. The user's detected language code is: {language_code}. You MUST respond in this language.
4. Use the following knowledge base if relevant, but feel free to use your general knowledge to answer any other questions:
{json.dumps(kb_context, indent=2, ensure_ascii=False)}
"""
        
        # Convert our history format to Gemini's format
        formatted_history = []
        for msg in chat_history:
            role = "model" if msg["role"] == "assistant" else "user"
            formatted_history.append({"role": role, "parts": [msg["content"]]})
            
        chat = model.start_chat(history=formatted_history)
        
        # Combine system prompt with the actual user message
        full_message = f"System Context:\n{system_prompt}\n\nUser Question:\n{prompt_text}"
        
        response = chat.send_message(full_message)
        return response.text
    except Exception as e:
        print(f"Error calling Gemini: {e}")
        return "I am sorry, I am unable to answer right now."

def sarvam_stt(audio_file_path):
    url = "https://api.sarvam.ai/speech-to-text"
    headers = {"api-subscription-key": os.getenv("SARVAM_API_KEY")}
    print(f"    [Sarvam STT] ▶ Input audio: {audio_file_path}")
    try:
        # Get language code from .env, default to 'en-IN' to prevent noise/silence auto-LID issues.
        # Set VOICE_LANGUAGE_CODE=auto in your .env if you wish to use multi-language auto-detection.
        lang_code_config = os.getenv("VOICE_LANGUAGE_CODE", "en-IN")
        
        with open(audio_file_path, "rb") as f:
            files = {"file": (audio_file_path, f, "audio/wav")}
            data = {"model": "saaras:v3"}
            if lang_code_config and lang_code_config.lower() != "auto":
                data["language_code"] = lang_code_config
                
            response = requests.post(url, headers=headers, files=files, data=data)
            
        if response.status_code == 200:
            result = response.json()
            transcript = result.get("transcript", "")
            lang_code = result.get("language_code", "en-IN")
            print(f"    [Sarvam STT] ◀ Transcript : '{transcript}'")
            print(f"    [Sarvam STT] ◀ Language   : '{lang_code}'")
            return transcript, lang_code
        else:
            print(f"    [Sarvam STT] ✗ HTTP {response.status_code}: {response.text}")
            return "", "en-IN"
    except Exception as e:
        print(f"    [Sarvam STT] ✗ Exception: {e}")
        return "", "en-IN"

def sarvam_tts(text, language_code, output_file_path):
    # Enforce a strict 490 character truncation safeguard to satisfy Sarvam TTS limit (max 500 characters)
    if len(text) > 490:
        text = text[:487] + "..."

    print(f"    [Sarvam TTS] ▶ Input text ({language_code}): '{text}'")
        
    url = "https://api.sarvam.ai/text-to-speech"
    headers = {
        "api-subscription-key": os.getenv("SARVAM_API_KEY"),
        "Content-Type": "application/json"
    }
    payload = {
        "inputs": [text],
        "target_language_code": language_code,
        "speaker": "priya",
        "pace": 1.0,
        "speech_sample_rate": 16000,
        "enable_preprocessing": True,
        "model": "bulbul:v3"
    }
    
    try:
        response = requests.post(url, headers=headers, json=payload)
        if response.status_code == 200:
            result = response.json()
            audio_base64 = result["audios"][0]
            import base64
            with open(output_file_path, "wb") as f:
                f.write(base64.b64decode(audio_base64))
            print(f"    [Sarvam TTS] ◀ Audio saved to: {output_file_path}")
            return True
        else:
            print(f"    [Sarvam TTS] ✗ HTTP {response.status_code}: {response.text}")
            return False
    except Exception as e:
        print(f"    [Sarvam TTS] ✗ Exception: {e}")
        return False
