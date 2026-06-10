const micBtn = document.getElementById('mic-btn');
const statusText = document.getElementById('status-text');
const chatContainer = document.getElementById('chat-container');

let mediaRecorder;
let audioChunks = [];
let isRecording = false;

micBtn.addEventListener('click', toggleRecording);

async function toggleRecording() {
    if (!isRecording) {
        await startRecording();
    } else {
        stopRecording();
    }
}

async function startRecording() {
    try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        mediaRecorder = new MediaRecorder(stream);
        audioChunks = [];

        mediaRecorder.ondataavailable = event => {
            if (event.data.size > 0) {
                audioChunks.push(event.data);
            }
        };

        mediaRecorder.onstop = async () => {
            statusText.textContent = "Processing...";
            const rawBlob = new Blob(audioChunks);
            
            try {
                // Convert WebM/OGG to true PCM WAV before sending to API
                const wavBlob = await convertWebMToWav(rawBlob);
                await sendAudioToAPI(wavBlob);
            } catch (err) {
                console.error("WAV conversion error:", err);
                statusText.textContent = "Error occurred";
            }
        };

        mediaRecorder.start();
        isRecording = true;
        micBtn.classList.add('recording');
        statusText.textContent = "Recording... Click to stop";
    } catch (err) {
        console.error("Microphone error:", err);
        alert("Please allow microphone access in your browser.");
    }
}

function stopRecording() {
    if (mediaRecorder && isRecording) {
        mediaRecorder.stop();
        mediaRecorder.stream.getTracks().forEach(track => track.stop());
        isRecording = false;
        micBtn.classList.remove('recording');
    }
}

async function sendAudioToAPI(audioBlob) {
    // Append user message placeholder
    const userMsg = addMessage("Thinking...", "user-msg");
    
    const formData = new FormData();
    formData.append("audio_file", audioBlob, "recording.wav");

    try {
        // Retrieve current session ID if exists
        let sessionId = localStorage.getItem('session_id') || '';
        const url = sessionId ? `/GetAnswer?session_id=${encodeURIComponent(sessionId)}` : '/GetAnswer';

        const response = await fetch(url, {
            method: 'POST',
            body: formData
        });

        if (!response.ok) {
            throw new Error(`Server error: ${response.statusText}`);
        }

        const data = await response.json();
        
        // Save the returned session ID for subsequent requests
        if (data.session_id) {
            localStorage.setItem('session_id', data.session_id);
        }
        
        // Update user message with transcript
        userMsg.textContent = data.transcript;
        
        // Add assistant message
        addMessage(data.answer_text, "assistant-msg");

        // Play audio
        playBase64Audio(data.audio_base64);
        statusText.textContent = "Ready";

    } catch (err) {
        console.error(err);
        statusText.textContent = "Error occurred";
        userMsg.textContent = "Failed to transcribe audio.";
    }
}

function addMessage(text, className) {
    const msgDiv = document.createElement('div');
    msgDiv.className = `message ${className}`;
    msgDiv.textContent = text;
    chatContainer.appendChild(msgDiv);
    chatContainer.scrollTop = chatContainer.scrollHeight;
    return msgDiv;
}

function playBase64Audio(base64Str) {
    // Determine mime type, typically wav
    const audio = new Audio(`data:audio/wav;base64,${base64Str}`);
    audio.play().catch(e => console.error("Error playing audio:", e));
}

// --- WAV CONVERSION HELPERS ---
async function convertWebMToWav(blob) {
    const audioContext = new (window.AudioContext || window.webkitAudioContext)();
    const arrayBuffer = await blob.arrayBuffer();
    const audioBuffer = await audioContext.decodeAudioData(arrayBuffer);
    return audioBufferToWav(audioBuffer);
}

function audioBufferToWav(buffer) {
    const numChannels = buffer.numberOfChannels;
    const sampleRate = buffer.sampleRate;
    const format = 1; // PCM
    const bitDepth = 16;
    
    let result;
    if (numChannels === 2) {
        result = interleave(buffer.getChannelData(0), buffer.getChannelData(1));
    } else {
        result = buffer.getChannelData(0);
    }
    return encodeWAV(result, format, sampleRate, numChannels, bitDepth);
}

function interleave(channelLeft, channelRight) {
    const length = channelLeft.length + channelRight.length;
    const result = new Float32Array(length);
    let inputIndex = 0;
    for (let index = 0; index < length; ) {
        result[index++] = channelLeft[inputIndex];
        result[index++] = channelRight[inputIndex];
        inputIndex++;
    }
    return result;
}

function encodeWAV(samples, format, sampleRate, numChannels, bitDepth) {
    const bytesPerSample = bitDepth / 8;
    const blockAlign = numChannels * bytesPerSample;
    const buffer = new ArrayBuffer(44 + samples.length * bytesPerSample);
    const view = new DataView(buffer);
    
    // RIFF chunk
    writeString(view, 0, 'RIFF');
    view.setUint32(4, 36 + samples.length * bytesPerSample, true);
    writeString(view, 8, 'WAVE');
    
    // fmt sub-chunk
    writeString(view, 12, 'fmt ');
    view.setUint32(16, 16, true);
    view.setUint16(20, format, true);
    view.setUint16(22, numChannels, true);
    view.setUint32(24, sampleRate, true);
    view.setUint32(28, sampleRate * blockAlign, true);
    view.setUint16(32, blockAlign, true);
    view.setUint16(34, bitDepth, true);
    
    // data sub-chunk
    writeString(view, 36, 'data');
    view.setUint32(40, samples.length * bytesPerSample, true);
    
    // PCM samples
    floatTo16BitPCM(view, 44, samples);
    return new Blob([view], { type: 'audio/wav' });
}

function writeString(view, offset, string) {
    for (let i = 0; i < string.length; i++) {
        view.setUint8(offset + i, string.charCodeAt(i));
    }
}

function floatTo16BitPCM(output, offset, input) {
    for (let i = 0; i < input.length; i++, offset += 2) {
        let s = Math.max(-1, Math.min(1, input[i]));
        output.setInt16(offset, s < 0 ? s * 0x8000 : s * 0x7FFF, true);
    }
}
