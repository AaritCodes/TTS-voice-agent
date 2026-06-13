import os
import requests
import google.generativeai as genai
import json
from pinecone import Pinecone

# Configure Gemini
def setup_gemini():
    genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

_pinecone_index = None

def get_pinecone_index():
    global _pinecone_index
    if _pinecone_index is None:
        try:
            api_key = os.getenv("PINECONE_API_KEY")
            index_name = os.getenv("PINECONE_INDEX_NAME", "voice-agent-kb")
            if api_key:
                pc = Pinecone(api_key=api_key)
                _pinecone_index = pc.Index(index_name)
        except Exception as e:
            print(f"Error connecting to Pinecone: {e}")
    return _pinecone_index

def query_pinecone(query_text, num_results=3):
    idx = get_pinecone_index()
    if idx is None:
        print("Warning: Pinecone index not initialized, skipping semantic search.")
        return ""
        
    try:
        # Generate query embedding using models/gemini-embedding-001 via HTTP REST API
        api_key = os.getenv("GEMINI_API_KEY")
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-embedding-001:embedContent?key={api_key}"
        payload = {
            "model": "models/gemini-embedding-001",
            "content": {
                "parts": [{
                    "text": query_text
                }]
            }
        }
        response = requests.post(url, json=payload)
        if response.status_code != 200:
            print(f"Error calling Gemini Embedding API: {response.text}")
            return ""
            
        query_vector = response.json()["embedding"]["values"]
        
        # Query Pinecone index
        response = idx.query(
            vector=query_vector,
            top_k=num_results,
            include_metadata=True
        )
        
        # Extract text from matches
        relevant_chunks = []
        for match in response.get("matches", []):
            if match.get("metadata") and "text" in match["metadata"]:
                relevant_chunks.append(match["metadata"]["text"])
                
        return "\n\n".join(relevant_chunks)
    except Exception as e:
        print(f"Error querying Pinecone: {e}")
        return ""

def get_gemini_response(prompt_text, chat_history, language_code, kb_context=None):
    try:
        model = genai.GenerativeModel('gemini-2.5-flash')
        
        # Fetch relevant chunks semantically from Pinecone
        relevant_context = query_pinecone(prompt_text)
        
        # Fall back to local kb_context (JSON) if Pinecone returns nothing
        if not relevant_context and kb_context:
            relevant_context = json.dumps(kb_context, indent=2, ensure_ascii=False)
            
        system_prompt = f"""You are a helpful multilingual voice assistant.
Rules:
1. Answer concisely and naturally for voice conversations.
2. The user's detected language code is: {language_code}. You MUST respond in this language.
3. If the user's question is related to the support guidelines or meeting notes, use the following retrieved context to answer:
{relevant_context}
If the question is unrelated to the context (e.g., general knowledge, small talk, or general advice), use your own knowledge to answer concisely and naturally. Do not refuse to answer general questions.
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
    url = "https://api.sarvam.ai/speech-to-text-translate" # typically it's this or speech-to-text
    # We will use /speech-to-text for native language, /speech-to-text-translate for english translation
    # Let's use speech-to-text
    url = "https://api.sarvam.ai/speech-to-text"
    headers = {"api-subscription-key": os.getenv("SARVAM_API_KEY")}
    try:
        with open(audio_file_path, "rb") as f:
            files = {"file": (audio_file_path, f, "audio/wav")}
            data = {"model": "saaras:v3"}
            response = requests.post(url, headers=headers, files=files, data=data)
            
        if response.status_code == 200:
            result = response.json()
            # If the API returns language_code, great. If not, default to en-IN for safety.
            return result.get("transcript", ""), result.get("language_code", "en-IN")
        else:
            print(f"Sarvam STT Error: {response.text}")
            return "", "en-IN"
    except Exception as e:
        print(f"Error calling Sarvam STT: {e}")
        return "", "en-IN"

def sarvam_tts(text, language_code, output_file_path):
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
            return True
        else:
            print(f"Sarvam TTS Error: {response.text}")
            return False
    except Exception as e:
        print(f"Error calling Sarvam TTS: {e}")
        return False

def get_gemini_response_stream(prompt_text, chat_history, language_code, kb_context=None):
    try:
        model = genai.GenerativeModel('gemini-2.5-flash')
        
        # Fetch relevant chunks semantically from Pinecone
        relevant_context = query_pinecone(prompt_text)
        
        # Fall back to local kb_context (JSON) if Pinecone returns nothing
        if not relevant_context and kb_context:
            relevant_context = json.dumps(kb_context, indent=2, ensure_ascii=False)
            
        system_prompt = f"""You are a helpful multilingual voice assistant.
Rules:
1. Answer concisely and naturally for voice conversations.
2. The user's detected language code is: {language_code}. You MUST respond in this language.
3. If the user's question is related to the support guidelines or meeting notes, use the following retrieved context to answer:
{relevant_context}
If the question is unrelated to the context (e.g., general knowledge, small talk, or general advice), use your own knowledge to answer concisely and naturally. Do not refuse to answer general questions.
"""
        
        # Convert our history format to Gemini's format
        formatted_history = []
        for msg in chat_history:
            role = "model" if msg["role"] == "assistant" else "user"
            formatted_history.append({"role": role, "parts": [msg["content"]]})
            
        chat = model.start_chat(history=formatted_history)
        
        # Combine system prompt with the actual user message
        full_message = f"System Context:\n{system_prompt}\n\nUser Question:\n{prompt_text}"
        
        response = chat.send_message(full_message, stream=True)
        for chunk in response:
            yield chunk.text
    except Exception as e:
        print(f"Error calling Gemini stream: {e}")
        yield "I am sorry, I am unable to answer right now."

_supabase_client = None

def get_supabase_client():
    global _supabase_client
    if _supabase_client is None:
        url = os.getenv("SUPABASE_URL")
        key = os.getenv("SUPABASE_KEY")
        if url and key:
            try:
                from supabase import create_client
    global _pinecone_index
    if _pinecone_index is None:
        try:
            api_key = os.getenv("PINECONE_API_KEY")
            index_name = os.getenv("PINECONE_INDEX_NAME", "voice-agent-kb")
            if api_key:
                pc = Pinecone(api_key=api_key)
                _pinecone_index = pc.Index(index_name)
        except Exception as e:
            print(f"Error connecting to Pinecone: {e}")
    return _pinecone_index

def query_pinecone(query_text, num_results=3):
    idx = get_pinecone_index()
    if idx is None:
        print("Warning: Pinecone index not initialized, skipping semantic search.")
        return ""
        
    try:
        # Generate query embedding using models/gemini-embedding-001 via HTTP REST API
        api_key = os.getenv("GEMINI_API_KEY")
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-embedding-001:embedContent?key={api_key}"
        payload = {
            "model": "models/gemini-embedding-001",
            "content": {
                "parts": [{
                    "text": query_text
                }]
            }
        }
        response = requests.post(url, json=payload)
        if response.status_code != 200:
            print(f"Error calling Gemini Embedding API: {response.text}")
            return ""
            
        query_vector = response.json()["embedding"]["values"]
        
        # Query Pinecone index
        response = idx.query(
            vector=query_vector,
            top_k=num_results,
            include_metadata=True
        )
        
        # Extract text from matches
        relevant_chunks = []
        for match in response.get("matches", []):
            if match.get("metadata") and "text" in match["metadata"]:
                relevant_chunks.append(match["metadata"]["text"])
                
        return "\n\n".join(relevant_chunks)
    except Exception as e:
        print(f"Error querying Pinecone: {e}")
        return ""

def get_gemini_response(prompt_text, chat_history, language_code, kb_context=None):
    try:
        model = genai.GenerativeModel('gemini-2.5-flash')
        
        # Fetch relevant chunks semantically from Pinecone
        relevant_context = query_pinecone(prompt_text)
        
        # Fall back to local kb_context (JSON) if Pinecone returns nothing
        if not relevant_context and kb_context:
            relevant_context = json.dumps(kb_context, indent=2, ensure_ascii=False)
            
        system_prompt = f"""You are a helpful multilingual voice assistant.
Rules:
1. Answer concisely and naturally for voice conversations.
2. The user's detected language code is: {language_code}. You MUST respond in this language.
3. If the user's question is related to the support guidelines or meeting notes, use the following retrieved context to answer:
{relevant_context}
If the question is unrelated to the context (e.g., general knowledge, small talk, or general advice), use your own knowledge to answer concisely and naturally. Do not refuse to answer general questions.
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
    url = "https://api.sarvam.ai/speech-to-text-translate" # typically it's this or speech-to-text
    # We will use /speech-to-text for native language, /speech-to-text-translate for english translation
    # Let's use speech-to-text
    url = "https://api.sarvam.ai/speech-to-text"
    headers = {"api-subscription-key": os.getenv("SARVAM_API_KEY")}
    try:
        with open(audio_file_path, "rb") as f:
            files = {"file": (audio_file_path, f, "audio/wav")}
            data = {"model": "saaras:v3"}
            response = requests.post(url, headers=headers, files=files, data=data)
            
        if response.status_code == 200:
            result = response.json()
            # If the API returns language_code, great. If not, default to en-IN for safety.
            return result.get("transcript", ""), result.get("language_code", "en-IN")
        else:
            print(f"Sarvam STT Error: {response.text}")
            return "", "en-IN"
    except Exception as e:
        print(f"Error calling Sarvam STT: {e}")
        return "", "en-IN"

def sarvam_tts(text, language_code, output_file_path):
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
            return True
        else:
            print(f"Sarvam TTS Error: {response.text}")
            return False
    except Exception as e:
        print(f"Error calling Sarvam TTS: {e}")
        return False

def get_gemini_response_stream(prompt_text, chat_history, language_code, kb_context=None):
    try:
        model = genai.GenerativeModel('gemini-2.5-flash')
        
        # Fetch relevant chunks semantically from Pinecone
        relevant_context = query_pinecone(prompt_text)
        
        # Fall back to local kb_context (JSON) if Pinecone returns nothing
        if not relevant_context and kb_context:
            relevant_context = json.dumps(kb_context, indent=2, ensure_ascii=False)
            
        system_prompt = f"""You are a helpful multilingual voice assistant.
Rules:
1. Answer concisely and naturally for voice conversations.
2. The user's detected language code is: {language_code}. You MUST respond in this language.
3. If the user's question is related to the support guidelines or meeting notes, use the following retrieved context to answer:
{relevant_context}
If the question is unrelated to the context (e.g., general knowledge, small talk, or general advice), use your own knowledge to answer concisely and naturally. Do not refuse to answer general questions.
"""
        
        # Convert our history format to Gemini's format
        formatted_history = []
        for msg in chat_history:
            role = "model" if msg["role"] == "assistant" else "user"
            formatted_history.append({"role": role, "parts": [msg["content"]]})
            
        chat = model.start_chat(history=formatted_history)
        
        # Combine system prompt with the actual user message
        full_message = f"System Context:\n{system_prompt}\n\nUser Question:\n{prompt_text}"
        
        response = chat.send_message(full_message, stream=True)
        for chunk in response:
            yield chunk.text
    except Exception as e:
        print(f"Error calling Gemini stream: {e}")
        yield "I am sorry, I am unable to answer right now."

_supabase_client = None

def get_supabase_client():
    global _supabase_client
    if _supabase_client is None:
        url = os.getenv("SUPABASE_URL")
        key = os.getenv("SUPABASE_KEY")
        if url and key:
            try:
                from supabase import create_client
                _supabase_client = create_client(url, key)
            except ImportError:
                print("Supabase package not installed.")
    return _supabase_client

def insert_call_log(data):
    try:
        import asyncio
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            asyncio.set_event_loop(asyncio.new_event_loop())

        client = get_supabase_client()
        if client:
            client.table("call_logs").insert(data).execute()
            print("Successfully saved call log to Supabase!")
        else:
            print("Supabase client not initialized. Call log not saved.")
    except Exception as e:
        print(f"Error inserting into Supabase: {e}")
