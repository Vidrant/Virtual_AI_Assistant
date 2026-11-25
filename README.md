# JARVIS AI Assistant

A voice-enabled AI assistant built with React/Vite and FastAPI. Simple requests like calculations, the time and the date are answered by local code, which is instant and uses no tokens. Everything else goes to a Groq-hosted language model. Each browser session keeps its own chat history.

Voice input uses Whisper speech-to-text and replies can be read aloud with the browser's built-in text-to-speech.

## One-time setup

1. Install **Python 3.11 or newer** and **Node.js** on Windows.
2. Open `backend/.env.example`, copy it to `backend/.env`, and replace the placeholder with your Groq API key. The chat assistant uses Groq for its language model.
3. Double-click `start_jarvis.bat`. It creates the Python environment, installs dependencies, builds the frontend, and starts JARVIS at `http://127.0.0.1:8000`.
4. Allow microphone access when the browser asks.

The first start installs `faster-whisper`; the first transcription downloads the `tiny.en` model. Once the model is cached, Whisper transcribes locally without sending the audio to a transcription service. You need an internet connection for the initial package/model downloads and for Groq-powered chat responses.

## Voice modes

The `TRANSCRIBE_WITH` setting in `backend/.env` decides where speech is turned into text:

| Setting | Where it runs | Used for |
|---|---|---|
| `TRANSCRIBE_WITH=local` (default) | `faster-whisper` on your own computer. Recordings never leave it, and it works offline. | Running JARVIS on your PC |
| `TRANSCRIBE_WITH=groq` | Groq's Whisper API (`whisper-large-v3-turbo`). Recordings are sent to Groq. | The online version on Render, whose free server is too small to run Whisper |

The backend reports its mode at `/health`, and the page adjusts its voice messages to match.

## Use voice

- Press the microphone button to start recording. Press the stop button when finished. JARVIS transcribes the recording and submits the recognized text to the Groq chat API.
- Press the speaker button on an assistant reply to hear it. Speech synthesis runs in the browser.
- `tiny.en` is small and English-only. To use Whisper's multilingual tiny model instead, change `WHISPER_MODEL=tiny.en` to `WHISPER_MODEL=tiny` in `backend/.env`, then restart the server. The model downloads the first time it is used.

To stop JARVIS, focus the terminal window running the server and press **Ctrl+C**. To start it next time, double-click `start_jarvis.bat` again.

## Test the voice flow

1. Start the app with `start_jarvis.bat` and wait for the browser page to load.
2. Click the microphone button, say a short phrase such as “What is 25 times 8?”, then click stop.
3. Confirm the recognized text appears as a chat message and JARVIS replies.
4. Click the speaker button beside the reply and confirm it is spoken aloud.
5. For offline transcription, disconnect the network after the first successful model download and repeat only the transcription step. Chat replies still need internet because the assistant uses Groq.

## Deploy online (Render + Vercel, both free)

The backend runs on **Render** and the website on **Vercel**. Deploy the backend first, because the website needs its address.

### 1. Backend on Render

Create a **Web Service** from this GitHub repository with these settings:

| Setting | Value |
|---|---|
| Language | Python 3 |
| Root Directory | *(leave empty)* |
| Build Command | `pip install -r backend/requirements.txt` |
| Start Command | `uvicorn main:app --app-dir backend --host 0.0.0.0 --port $PORT` |
| Instance Type | Free |
| Health Check Path | `/health` |

Environment variables:

| Name | Value |
|---|---|
| `GROQ_API_KEY` | your Groq API key |
| `TRANSCRIBE_WITH` | `groq` |
| `FRONTEND_ORIGINS` | your Vercel address, e.g. `https://jarvis.vercel.app` (add it after step 2) |

`backend/requirements.txt` leaves out `faster-whisper`, so the online server stays small. `start_jarvis.bat` installs `backend/requirements-local.txt`, which adds it back for local use.

### 2. Website on Vercel

Import the same GitHub repository as a new project:

| Setting | Value |
|---|---|
| Root Directory | `frontend` |
| Framework Preset | Vite (detected automatically) |
| Environment variable `VITE_API_URL` | your Render address, e.g. `https://jarvis-backend.onrender.com` |

After Vercel gives you the website address, put it in `FRONTEND_ORIGINS` on Render. This is the CORS setting that lets the website call the backend.

### Free-plan behaviour

- The Render backend sleeps after 15 minutes without visitors and takes about a minute to wake. The website starts waking it as soon as the page opens, and the header shows **WAKING UP…** until it is ready.
- Chat history is kept in the backend's memory, so it resets whenever the backend sleeps or restarts.
- Anyone with the website address can chat using your Groq key's free-tier limits, so share the link carefully.

## Notes

- In `local` mode, recordings go from the browser to the FastAPI server on your computer; the audio is not sent to Groq. Only the resulting transcript is sent to Groq when it is submitted as a chat prompt.
- The microphone works on localhost and on HTTPS sites in modern browsers. Keep recordings under 20 MB.
- Never commit `backend/.env`; `.gitignore` excludes it. Do not paste your API key into chat or a public repository. Online, enter it only in Render's environment settings.
