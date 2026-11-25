# JARVIS AI Assistant — Local Voice Setup

This copy adds local Whisper speech-to-text and browser text-to-speech to the existing React/Vite + FastAPI app. It also keeps each browser session's chat history separate.

## One-time setup

1. Install **Python 3.11 or newer** and **Node.js** on Windows.
2. Open `backend/.env.example`, copy it to `backend/.env`, and replace the placeholder with your Groq API key. The chat assistant still uses Groq for its language model.
3. Double-click `start_jarvis.bat`. It creates the Python environment, installs dependencies, builds the frontend, and starts JARVIS at `http://127.0.0.1:8000`.
4. Allow microphone access when the browser asks.

The first start installs `faster-whisper`; the first transcription downloads the `tiny.en` model. Once the model is cached, Whisper transcribes locally without sending the audio to a transcription service. You need an internet connection for the initial package/model downloads and for Groq-powered chat responses.

## Use voice

- Press the microphone button to start recording. Press the stop button when finished. JARVIS transcribes locally and submits the recognized text to the existing Groq chat API.
- Press the speaker button on an assistant reply to hear it. Speech synthesis runs in the browser.
- `tiny.en` is small and English-only. To use Whisper's multilingual tiny model instead, change `WHISPER_MODEL=tiny.en` to `WHISPER_MODEL=tiny` in `backend/.env`, then restart the server. The model downloads the first time it is used.

To stop JARVIS, focus the terminal window running the server and press **Ctrl+C**. To start it next time, double-click `start_jarvis.bat` again.

## Test the voice flow

1. Start the app with `start_jarvis.bat` and wait for the browser page to load.
2. Click the microphone button, say a short phrase such as “What is 25 times 8?”, then click stop.
3. Confirm the recognized text appears as a chat message and JARVIS replies.
4. Click the speaker button beside the reply and confirm it is spoken aloud.
5. For offline transcription, disconnect the network after the first successful model download and repeat only the transcription step. Chat replies still need internet because the current assistant uses Groq.

## Notes

- Recordings are sent from the browser to the local FastAPI server at `127.0.0.1`; the audio is not sent to Groq. Only the resulting transcript is sent to Groq when it is submitted as a chat prompt.
- The microphone works on localhost in modern browsers. Keep recordings under 20 MB.
- The local model is intended for running JARVIS on your own computer. Free cloud hosts do not provide enough CPU/RAM for reliable local Whisper inference.
- Never commit `backend/.env`; `.gitignore` excludes it. Do not paste your API key into chat or a public repository.

