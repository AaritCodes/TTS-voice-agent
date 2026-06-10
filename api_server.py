import os
import json
import base64
import tempfile
import uuid
from fastapi import FastAPI, UploadFile, File, HTTPException, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse
from dotenv import load_dotenv

from api_clients import setup_gemini, get_gemini_response, sarvam_stt, sarvam_tts

load_dotenv()
setup_gemini()

app = FastAPI(title="Voice Assistant API", description="API for STT -> Gemini -> TTS pipeline")

os.makedirs("static", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
def read_root():
    return RedirectResponse(url="/static/index.html")

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

# Thread-safe dictionary to maintain isolated chat histories for individual user sessions
chat_histories = {}
kb = load_knowledge_base()

@app.post("/GetAnswer")
async def get_answer(
    audio_file: UploadFile = File(...),
    session_id: str = Query(None, description="Unique session ID for the user's chat history")
):
    if not audio_file.filename.endswith(('.wav', '.mp3', '.ogg', '.flac')):
        raise HTTPException(status_code=400, detail="Unsupported audio format")
    
    # If no session ID is supplied, generate a unique one
    if not session_id:
        session_id = str(uuid.uuid4())
        
    # Get or create the isolated chat history for this specific session
    session_history = chat_histories.setdefault(session_id, [])
    
    # Save the uploaded file temporarily
    temp_id = str(uuid.uuid4())
    input_path = os.path.join(tempfile.gettempdir(), f"input_{temp_id}.wav")
    output_path = os.path.join(tempfile.gettempdir(), f"output_{temp_id}.wav")
    
    try:
        # Write uploaded file
        with open(input_path, "wb") as buffer:
            buffer.write(await audio_file.read())
            
        # STT
        print(f"[{temp_id}] Transcribing audio...")
        transcript, lang_code = sarvam_stt(input_path)
        if not transcript:
            raise HTTPException(status_code=400, detail="Could not understand audio")
            
        print(f"[{temp_id}] User said: {transcript} ({lang_code})")
        
        # LLM
        mapped_lang = LANGUAGE_MAP.get(lang_code, "en-IN")
        answer = get_gemini_response(transcript, session_history, mapped_lang, kb)
        print(f"[{temp_id}] Assistant says: {answer}")
        
        # Update session-specific history
        session_history.append({"role": "user", "content": transcript})
        session_history.append({"role": "assistant", "content": answer})
        
        # TTS
        print(f"[{temp_id}] Generating audio...")
        if not sarvam_tts(answer, mapped_lang, output_path):
            raise HTTPException(status_code=500, detail="Failed to generate audio response")
            
        # Read the generated audio and encode it
        with open(output_path, "rb") as f:
            audio_bytes = f.read()
            audio_base64 = base64.b64encode(audio_bytes).decode('utf-8')
            
        return {
            "session_id": session_id,
            "transcript": transcript,
            "detected_language": lang_code,
            "answer_text": answer,
            "audio_base64": audio_base64
        }
        
    finally:
        # Cleanup temp files
        if os.path.exists(input_path):
            try:
                os.remove(input_path)
            except Exception:
                pass
        if os.path.exists(output_path):
            try:
                os.remove(output_path)
            except Exception:
                pass
