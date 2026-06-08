import sounddevice as sd
import soundfile as sf
import speech_recognition as sr
import numpy as np

def listen_for_wake_word(wake_word="assistant"):
    r = sr.Recognizer()
    print(f"Listening for wake word: '{wake_word}'...")
    while True:
        try:
            # Listen in short chunks using sounddevice instead of pyaudio
            samplerate = 16000
            duration = 3
            myrecording = sd.rec(int(duration * samplerate), samplerate=samplerate, channels=1, dtype='int16')
            sd.wait()
            
            # Convert to speech_recognition AudioData format (2 bytes per sample for int16)
            audio_data = sr.AudioData(myrecording.tobytes(), samplerate, 2)
            
            try:
                text = r.recognize_google(audio_data).lower()
                if wake_word in text:
                    print(f"Wake word '{wake_word}' detected!")
                    return True
            except sr.UnknownValueError:
                pass
            except sr.RequestError:
                pass
        except Exception as e:
            print(f"Microphone error: {e}")
            return False

def record_audio(filename="input.wav", duration=6, samplerate=16000):
    print(f"Recording your voice for {duration} seconds... Please speak now.")
    try:
        myrecording = sd.rec(int(duration * samplerate), samplerate=samplerate, channels=1, dtype='int16')
        sd.wait()
        print("Recording complete.")
        sf.write(filename, myrecording, samplerate)
        return filename
    except Exception as e:
        print(f"Error recording audio: {e}")
        return None

def play_audio(filename="output.wav"):
    try:
        data, fs = sf.read(filename, dtype='float32')
        sd.play(data, fs)
        sd.wait()
    except Exception as e:
        print(f"Error playing audio: {e}")
