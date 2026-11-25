import { useState, useRef, useEffect } from "react";
import "./App.css";

const API_URL = window.location.port === "8000"
  ? window.location.origin
  : import.meta.env.VITE_API_URL || window.location.origin;

function App() {
  const [conversationId] = useState(() => {
    const storageKey = "jarvisConversationId";
    let id = sessionStorage.getItem(storageKey);
    if (!id) {
      id = crypto.randomUUID();
      sessionStorage.setItem(storageKey, id);
    }
    return id;
  });

  const [messages, setMessages] = useState([
    {
      role: "assistant",
      content:
        "Hello! I'm JARVIS. How can I assist you today?",
    },
  ]);

  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [speakingIndex, setSpeakingIndex] = useState(null);
  const [recording, setRecording] = useState(false);
  const [transcribing, setTranscribing] = useState(false);
  const [voiceError, setVoiceError] = useState("");

  // Reference to the actual chat container
  const chatAreaRef = useRef(null);
  const recorderRef = useRef(null);
  const streamRef = useRef(null);
  const audioChunksRef = useRef([]);

  const speakReply = (text, index) => {
    if (!("speechSynthesis" in window)) return;
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.onstart = () => setSpeakingIndex(index);
    utterance.onend = () => setSpeakingIndex(null);
    utterance.onerror = () => setSpeakingIndex(null);
    window.speechSynthesis.speak(utterance);
  };

  // ============================================================
  // SCROLL ONLY THE CHAT AREA
  // ============================================================

  useEffect(() => {
    const chatArea = chatAreaRef.current;

    if (!chatArea) return;

    chatArea.scrollTo({
      top: chatArea.scrollHeight,
      behavior: "smooth",
    });
  }, [messages, loading]);


  // ============================================================
  // SEND MESSAGE
  // ============================================================

  const sendMessage = async (message = input) => {
    const text = message.trim();

    if (!text || loading) return;

    // Add user message immediately
    setMessages((previous) => [
      ...previous,
      {
        role: "user",
        content: text,
      },
    ]);

    setInput("");
    setLoading(true);

    try {
      const response = await fetch(`${API_URL}/chat`, {
        method: "POST",

        headers: {
          "Content-Type": "application/json",
        },

        body: JSON.stringify({
          message: text,
          conversation_id: conversationId,
        }),
      });

      if (!response.ok) {
        throw new Error(
          `Server returned ${response.status}`
        );
      }

      const data = await response.json();

      setMessages((previous) => [
        ...previous,
        {
          role: "assistant",
          content:
            data.response ||
            "I couldn't generate a response.",
        },
      ]);
    } catch (error) {
      console.error(error);

      setMessages((previous) => [
        ...previous,
        {
          role: "assistant",
          content:
            "I'm unable to connect to the JARVIS backend right now.",
        },
      ]);
    } finally {
      setLoading(false);
    }
  };


  // ============================================================
  // LOCAL WHISPER SPEECH-TO-TEXT
  // ============================================================

  const toggleRecording = async () => {
    setVoiceError("");

    if (recording && recorderRef.current) {
      recorderRef.current.stop();
      setRecording(false);
      return;
    }

    if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) {
      setVoiceError("This browser does not support microphone recording.");
      return;
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
      audioChunksRef.current = [];
      const recorder = new MediaRecorder(stream);
      recorderRef.current = recorder;

      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) audioChunksRef.current.push(event.data);
      };

      recorder.onstop = async () => {
        stream.getTracks().forEach((track) => track.stop());
        streamRef.current = null;
        const blob = new Blob(audioChunksRef.current, {
          type: recorder.mimeType || "audio/webm",
        });
        if (!blob.size) return;

        const extension = blob.type.includes("ogg") ? "ogg" : blob.type.includes("mp4") ? "m4a" : "webm";
        const formData = new FormData();
        formData.append("audio", blob, `recording.${extension}`);
        setTranscribing(true);

        try {
          const response = await fetch(`${API_URL}/transcribe`, {
            method: "POST",
            body: formData,
          });
          const data = await response.json();
          if (!response.ok) throw new Error(data.detail || "Transcription failed.");
          const transcript = (data.text || "").trim();
          if (!transcript) {
            setVoiceError("No speech was detected. Try again.");
            return;
          }
          setInput(transcript);
          await sendMessage(transcript);
        } catch (error) {
          console.error(error);
          setVoiceError(error.message || "Local transcription failed.");
        } finally {
          setTranscribing(false);
        }
      };

      recorder.start();
      setRecording(true);
    } catch (error) {
      console.error(error);
      setVoiceError("Microphone access was blocked or unavailable.");
    }
  };


  useEffect(() => () => {
    if (recorderRef.current?.state === "recording") recorderRef.current.stop();
    streamRef.current?.getTracks().forEach((track) => track.stop());
    if ("speechSynthesis" in window) window.speechSynthesis.cancel();
  }, []);


  // ============================================================
  // ENTER KEY
  // ============================================================

  const handleKeyDown = (event) => {
    if (
      event.key === "Enter" &&
      !event.shiftKey
    ) {
      event.preventDefault();

      sendMessage();
    }
  };


  // ============================================================
  // CLEAR CONVERSATION
  // ============================================================

  const clearChat = () => {
    if ("speechSynthesis" in window) window.speechSynthesis.cancel();
    setSpeakingIndex(null);
    fetch(`${API_URL}/clear`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ conversation_id: conversationId }),
    }).catch((error) => console.error(error));
    setMessages([
      {
        role: "assistant",
        content:
          "Conversation cleared. How can I help you?",
      },
    ]);
  };


  // ============================================================
  // QUICK ACTIONS
  // ============================================================

  const quickActions = [
    "What is the time?",
    "Calculate 25 * 8",
    "Explain machine learning",
    "Search latest AI news",
  ];


  // ============================================================
  // UI
  // ============================================================

  return (
    <div className="app">

      {/* Background decoration */}
      <div className="background-glow glow-one"></div>

      <div className="background-glow glow-two"></div>


      {/* Main JARVIS container */}
      <div className="jarvis-container">


        {/* ======================================================
            HEADER
        ====================================================== */}

        <header className="header">

          <div className="brand">

            <div className="jarvis-logo">
              J
            </div>

            <div>

              <h1>JARVIS</h1>

              <div className="status">

                <span className="status-dot"></span>

                ONLINE

              </div>

            </div>

          </div>


          <button
            className="clear-button"
            onClick={clearChat}
          >
            Clear
          </button>

        </header>


        {/* ======================================================
            CHAT AREA

            IMPORTANT:
            This is now the ONLY element that gets scrolled.
        ====================================================== */}

        <main
          className="chat-area"
          ref={chatAreaRef}
        >

          {messages.map((message, index) => (

            <div
              key={index}
              className={`message-row ${
                message.role === "user"
                  ? "user-row"
                  : "assistant-row"
              }`}
            >

              {/* Assistant avatar */}
              {message.role === "assistant" && (
                <div className="avatar assistant-avatar">
                  J
                </div>
              )}


              {/* Message */}
              <div
                className={`message ${
                  message.role === "user"
                    ? "user-message"
                    : "assistant-message"
                }`}
              >
                {message.content}
              </div>

              {message.role === "assistant" && (
                <button
                  className="speak-button"
                  type="button"
                  onClick={() => speakReply(message.content, index)}
                  aria-label={speakingIndex === index ? "Replay response" : "Speak response"}
                  title="Read this response aloud"
                >
                  {speakingIndex === index ? "🔊" : "▶"}
                </button>
              )}

            </div>

          ))}


          {/* Loading indicator */}
          {loading && (

            <div className="message-row assistant-row">

              <div className="avatar assistant-avatar">
                J
              </div>

              <div className="message assistant-message typing">

                <span></span>
                <span></span>
                <span></span>

              </div>

            </div>

          )}

        </main>


        {/* ======================================================
            QUICK ACTIONS
        ====================================================== */}

        <div className="quick-actions">

          {quickActions.map((action, index) => (

            <button
              key={index}
              onClick={() => sendMessage(action)}
              disabled={loading}
            >
              {action}
            </button>

          ))}

        </div>


        {/* ======================================================
            INPUT
        ====================================================== */}

        <div className="input-section">

          <div className="input-container">

            <textarea
              value={input}
              onChange={(event) =>
                setInput(event.target.value)
              }
              onKeyDown={handleKeyDown}
              placeholder="Ask JARVIS anything..."
              rows="1"
              disabled={loading}
            />

            <button
              className={`mic-button${recording ? " is-recording" : ""}`}
              type="button"
              onClick={toggleRecording}
              disabled={loading || transcribing}
              aria-label={recording ? "Stop recording" : "Start voice input"}
              title={recording ? "Stop and transcribe" : "Speak to JARVIS (processed locally)"}
            >
              {recording ? "■" : "🎙"}
            </button>

            <button
              className="send-button"
              onClick={() => sendMessage()}
              disabled={
                !input.trim() || loading
              }
            >
              ➤
            </button>

          </div>


          <p className="input-hint">
            JARVIS can calculate, search the web,
            answer questions and more.
          </p>
          {(recording || transcribing) && (
            <p className="voice-status" role="status">
              {recording ? "Listening — press stop when finished." : "Transcribing locally… first use may take longer while the model downloads."}
            </p>
          )}
          {voiceError && <p className="voice-error" role="alert">{voiceError}</p>}

        </div>

      </div>

    </div>
  );
}

export default App;
