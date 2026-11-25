import os
import time
import ast
import operator
import io
from functools import lru_cache
from pathlib import Path

from datetime import datetime

from dotenv import load_dotenv
from groq import Groq

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel


# ============================================================
# ENVIRONMENT / GROQ
# ============================================================

load_dotenv()

API_KEY = os.getenv("GROQ_API_KEY")

if not API_KEY:
    raise ValueError(
        "GROQ_API_KEY not found. "
        "Make sure your .env file contains your Groq API key."
    )

client = Groq(api_key=API_KEY)

MODEL_NAME = "openai/gpt-oss-120b"

MAX_HISTORY_MESSAGES = 20

MAX_RETRIES = 3
RETRY_DELAY = 2


# ============================================================
# FASTAPI APP
# ============================================================

app = FastAPI(
    title="JARVIS AI Assistant API",
    description="Backend API for the JARVIS AI Virtual Assistant",
    version="1.0.0"
)


# ============================================================
# CORS
# ============================================================

frontend_origins = [
    origin.strip()
    for origin in os.getenv(
        "FRONTEND_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173",
    ).split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=frontend_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)


# ============================================================
# REQUEST MODEL
# ============================================================

class ChatRequest(BaseModel):
    message: str
    conversation_id: str


class ClearRequest(BaseModel):
    conversation_id: str


# ============================================================
# SPEECH-TO-TEXT SETTINGS
# ============================================================

# "local" = faster-whisper on this computer (private, works offline)
# "groq"  = Groq's Whisper API (for small online servers like Render)
TRANSCRIBE_WITH = os.getenv("TRANSCRIBE_WITH", "local").strip().lower()

if TRANSCRIBE_WITH not in ("local", "groq"):
    raise ValueError(
        "TRANSCRIBE_WITH must be 'local' or 'groq', "
        f"but it is '{TRANSCRIBE_WITH}'."
    )

MAX_AUDIO_BYTES = 20 * 1024 * 1024
WHISPER_MODEL_NAME = os.getenv("WHISPER_MODEL", "tiny.en")
GROQ_WHISPER_MODEL = "whisper-large-v3-turbo"
SUPPORTED_AUDIO_EXTENSIONS = {
    ".flac", ".mp3", ".mp4", ".mpeg", ".mpga", ".m4a", ".ogg", ".wav", ".webm"
}


@lru_cache(maxsize=1)
def get_whisper_model():
    # Imported here instead of at the top of the file, so the online
    # server (which uses Groq) doesn't need faster-whisper installed.
    from faster_whisper import WhisperModel

    # The model downloads once on first use, then loads from the local cache.
    return WhisperModel(
        WHISPER_MODEL_NAME,
        device="cpu",
        compute_type="int8",
    )


def transcribe_locally(audio_bytes):
    segments, _info = get_whisper_model().transcribe(
        io.BytesIO(audio_bytes),
        beam_size=1,
        vad_filter=True,
    )
    return " ".join(segment.text.strip() for segment in segments).strip()


def transcribe_with_groq(audio_bytes, filename):
    # Groq uses the filename's extension (.webm, .wav, ...) to read the audio
    transcription = client.audio.transcriptions.create(
        file=(filename, audio_bytes),
        model=GROQ_WHISPER_MODEL,
        language="en",
        temperature=0.0,
    )
    return transcription.text.strip()


@app.post("/transcribe")
async def transcribe_audio(audio: UploadFile = File(...)):
    filename = audio.filename or "recording.webm"
    extension = os.path.splitext(filename.lower())[1]
    if extension not in SUPPORTED_AUDIO_EXTENSIONS:
        raise HTTPException(status_code=415, detail="Unsupported audio format.")

    audio_bytes = await audio.read(MAX_AUDIO_BYTES + 1)
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="The recording is empty.")
    if len(audio_bytes) > MAX_AUDIO_BYTES:
        raise HTTPException(status_code=413, detail="Keep recordings under 20 MB.")

    try:
        if TRANSCRIBE_WITH == "groq":
            transcript = transcribe_with_groq(audio_bytes, filename)
        else:
            transcript = transcribe_locally(audio_bytes)

        return {"text": transcript}
    except Exception as error:
        print(f"TRANSCRIPTION ERROR ({TRANSCRIBE_WITH}):", error)
        raise HTTPException(
            status_code=422,
            detail="Could not transcribe this recording. Try recording again.",
        ) from error


# ============================================================
# SYSTEM PROMPT
# ============================================================

SYSTEM_PROMPT = """
You are JARVIS, a helpful AI virtual assistant.

Your responsibilities:

- Answer questions clearly and accurately.
- Maintain context from the conversation.
- Be concise unless the user asks for detail.
- Help with programming, AI, data science,
  academics and general tasks.
- Do not invent information.
- Do not perform mathematical calculations manually
  when a calculator result is already provided.
- When given web-search results, use those results
  to provide a current and accurate answer.
"""


# ============================================================
# CONVERSATION HISTORY
# ============================================================

conversations = {}


def new_conversation():
    return [
        {
            "role": "system",
            "content": SYSTEM_PROMPT
        }
    ]


def reset_conversation(conversation_id):
    conversations[conversation_id] = new_conversation()


# ============================================================
# TIME / DATE FUNCTIONS
# ============================================================

def get_time():
    now = datetime.now()

    return now.strftime("%I:%M:%S %p")


def get_date():
    now = datetime.now()

    return now.strftime("%A, %d %B %Y")


def get_datetime():
    now = datetime.now()

    return now.strftime("%A, %d %B %Y, %I:%M:%S %p")


# ============================================================
# SAFE CALCULATOR
# ============================================================

OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Mod: operator.mod,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
    ast.Pow: operator.pow
}

# Limits that stop huge powers (like 9 ** 9 ** 9) from freezing the server
MAX_EXPONENT = 100
MAX_POWER_BASE = 1_000_000


def evaluate_node(node):

    if isinstance(node, ast.Constant):

        if isinstance(node.value, (int, float)):

            return node.value

        raise ValueError("Only numbers are allowed.")

    if isinstance(node, ast.UnaryOp):

        operator_type = type(node.op)

        if operator_type not in OPERATORS:
            raise ValueError("Unsupported operator.")

        operand = evaluate_node(node.operand)

        return OPERATORS[operator_type](operand)

    if isinstance(node, ast.BinOp):

        operator_type = type(node.op)

        if operator_type not in OPERATORS:
            raise ValueError("Unsupported operator.")

        left = evaluate_node(node.left)
        right = evaluate_node(node.right)

        if operator_type in (ast.Div, ast.Mod) and right == 0:
            raise ValueError("Cannot divide by zero.")

        if operator_type == ast.Pow:
            if abs(right) > MAX_EXPONENT or abs(left) > MAX_POWER_BASE:
                raise ValueError("That number is too large to calculate.")

        return OPERATORS[operator_type](left, right)

    raise ValueError("Invalid mathematical expression.")


def safe_calculate(expression):

    expression = expression.strip()

    # Remove punctuation accidentally added by the user
    expression = expression.rstrip("?!., ")

    # Prevent extremely large expressions
    if len(expression) > 200:
        raise ValueError("Expression is too long.")

    try:

        tree = ast.parse(
            expression,
            mode="eval"
        )

        result = evaluate_node(tree.body)

        if isinstance(result, complex):
            raise ValueError("The answer is not a real number.")

        if isinstance(result, float):

            result = round(result, 10)

        return result

    except ZeroDivisionError:

        raise ValueError("Cannot divide by zero.")

    except ValueError:

        # evaluate_node already wrote a clear message
        # (e.g. "Cannot divide by zero."), so pass it on unchanged
        raise

    except Exception:

        raise ValueError(
            "Invalid mathematical expression."
        )


# ============================================================
# COMMAND NORMALIZATION
# ============================================================

def normalize_command(text):

    command = text.lower().strip()

    # Fix:
    # What is the time?
    # What is the time!
    # What's the date?
    command = command.rstrip("?!., ")

    return command


# ============================================================
# CALCULATION DETECTION
# ============================================================

def looks_like_calculation(text):

    expression = extract_expression(text)

    # 1. Must contain at least one digit
    if not any(character.isdigit() for character in expression):
        return False

    # 2. Must contain at least one mathematical operator
    math_symbols = "+-*/%"

    if not any(symbol in expression for symbol in math_symbols):
        return False

    # 3. Every character must belong to a math expression
    allowed_characters = set("0123456789+-*/%.() ")

    if not all(character in allowed_characters for character in expression):
        return False

    return True


# ============================================================
# EXTRACT CALCULATION EXPRESSION
# ============================================================

def extract_expression(text):

    expression = normalize_command(text)

    phrases_to_remove = [
        "calculate",
        "compute",
        "solve",
        "evaluate",
        "what is",
        "what's",
        "how much is"
    ]

    for phrase in phrases_to_remove:

        expression = expression.replace(
            phrase,
            ""
        )

    # Let users type 2^10 as well as 2 ** 10
    expression = expression.replace("^", "**")

    expression = expression.strip()

    return expression


# ============================================================
# NORMAL GROQ REQUEST
# ============================================================

def call_groq(history):

    for attempt in range(MAX_RETRIES):

        try:

            response = client.chat.completions.create(

                model=MODEL_NAME,

                messages=history,

                temperature=0.3,

                max_tokens=1024
            )

            return response.choices[0].message.content

        except Exception as error:

            error_text = str(error)

            # Rate limit
            if "429" in error_text:

                return (
                    "I'm currently rate-limited by Groq. "
                    "Please try again shortly."
                )

            # Temporary service problem
            if "503" in error_text:

                if attempt < MAX_RETRIES - 1:

                    time.sleep(RETRY_DELAY)

                    continue

                return (
                    "Groq is temporarily unavailable. "
                    "Please try again in a moment."
                )

            return (
                "Sorry, I encountered an error while "
                "processing your request."
            )

    return "Unable to get a response."


# ============================================================
# BROWSER SEARCH
# ============================================================

def call_groq_browser_search(query):

    try:

        response = client.chat.completions.create(

            model=MODEL_NAME,

            messages=[
                {
                    "role": "system",
                    "content": """
You are JARVIS's web search assistant.

Use browser search to find current information
from the web.

Instructions:

- Search the web for the user's query.
- Prefer recent and reliable information.
- Summarize the important findings clearly.
- Mention dates when relevant.
- Do not pretend you searched if the search failed.
- Keep the response concise unless more detail is requested.
"""
                },
                {
                    "role": "user",
                    "content": query
                }
            ],

            # Browser search requires temperature 1
            temperature=1,

            max_completion_tokens=2048,

            tool_choice="required",

            tools=[
                {
                    "type": "browser_search"
                }
            ]
        )

        return response.choices[0].message.content

    except Exception as error:

        error_text = str(error)

        if "429" in error_text:

            return (
                "The web search request was rate-limited. "
                "Please try again shortly."
            )

        if "503" in error_text:

            return (
                "The web search service is temporarily "
                "unavailable. Please try again shortly."
            )

        return (
            "I couldn't complete the web search right now. "
            "Please try again."
        )


# ============================================================
# SEARCH DETECTION
# ============================================================

def is_search_command(command):

    search_commands = (
        "search ",
        "search",
        "search for ",
        "look up ",
        "look for ",
        "find latest ",
        "find current ",
        "latest news ",
        "latest "
    )

    return command.startswith(search_commands)


# ============================================================
# EXTRACT SEARCH QUERY
# ============================================================

def extract_search_query(text):

    query = text.strip()

    prefixes = [
        "search for ",
        "search ",
        "look up ",
        "look for ",
        "find latest ",
        "find current ",
        "latest news ",
        "latest "
    ]

    lower_query = query.lower()

    for prefix in prefixes:

        if lower_query.startswith(prefix):

            query = query[len(prefix):]

            break

    query = query.strip()

    return query


# ============================================================
# MAIN MESSAGE PROCESSING
# ============================================================

def process_message(user_message, history):

    command = normalize_command(user_message)

    # --------------------------------------------------------
    # 1. CALCULATOR
    # --------------------------------------------------------

    if looks_like_calculation(user_message):

        try:

            expression = extract_expression(
                user_message
            )

            result = safe_calculate(
                expression
            )

            return f"The answer is {result}"

        except ValueError as error:

            return str(error)

    # --------------------------------------------------------
    # 2. TIME
    # --------------------------------------------------------

    if command in (
        "time",
        "what time is it",
        "current time",
        "what is the time",
        "what is the time rn",
        "what time is it rn",
        "time rn",
        "what's the time",
        "what's the time rn"
    ):

        return f"The current time is {get_time()}."

    # --------------------------------------------------------
    # 3. DATE
    # --------------------------------------------------------

    if command in (
        "date",
        "today",
        "today's date",
        "todays date",
        "what is today's date",
        "what's today's date",
        "what is the date",
        "what's the date"
    ):

        return f"Today's date is {get_date()}."

    # --------------------------------------------------------
    # 4. DATE + TIME
    # --------------------------------------------------------

    if command in (
        "datetime",
        "date and time",
        "date time",
        "current date and time"
    ):

        return (
            f"The current date and time is "
            f"{get_datetime()}."
        )

    # --------------------------------------------------------
    # 5. WEB SEARCH
    # --------------------------------------------------------

    if is_search_command(command):

        search_query = extract_search_query(
            user_message
        )

        if not search_query:

            return (
                "What would you like me to search for?"
            )

        # Add user request to conversation history
        history.append(
            {
                "role": "user",
                "content": user_message
            }
        )

        search_result = call_groq_browser_search(
            search_query
        )

        # Store search result in history
        history.append(
            {
                "role": "assistant",
                "content": search_result
            }
        )

        # Keep history under control
        if len(history) > MAX_HISTORY_MESSAGES + 1:
            history[:] = [history[0]] + history[-MAX_HISTORY_MESSAGES:]

        return search_result

    # --------------------------------------------------------
    # 6. NORMAL AI REQUEST
    # --------------------------------------------------------

    history.append(
        {
            "role": "user",
            "content": user_message
        }
    )

    # Limit conversation history
    if len(history) > MAX_HISTORY_MESSAGES + 1:
        history[:] = [history[0]] + history[-MAX_HISTORY_MESSAGES:]

    answer = call_groq(history)

    history.append(
        {
            "role": "assistant",
            "content": answer
        }
    )

    return answer


# ============================================================
# CHAT ENDPOINT
# ============================================================

@app.post("/chat")
async def chat(request: ChatRequest):

    user_message = request.message.strip()

    if not user_message:

        return {
            "response": "Please enter a message."
        }

    # Exit commands
    if user_message.lower() in (
        "exit",
        "quit",
        "bye"
    ):

        return {
            "response": "Goodbye! 👋"
        }

    try:

        history = conversations.setdefault(
            request.conversation_id,
            new_conversation(),
        )
        answer = process_message(user_message, history)

        return {
            "response": answer
        }

    except Exception as error:

        print(
            "ERROR:",
            error
        )

        return {
            "response": (
                "Sorry, something went wrong "
                "while processing your request."
            )
        }


# ============================================================
# CLEAR CONVERSATION
# ============================================================

@app.post("/clear")
async def clear_chat(request: ClearRequest):
    reset_conversation(request.conversation_id)

    return {
        "message": "Conversation cleared."
    }


# ============================================================
# ROOT
# ============================================================

@app.get("/")
async def root():
    index_file = Path(__file__).resolve().parent.parent / "frontend" / "dist" / "index.html"
    if index_file.exists():
        return FileResponse(index_file)

    return {
        "message": "JARVIS AI Assistant API is online.",
        "model": MODEL_NAME
    }


# ============================================================
# HEALTH CHECK
# ============================================================

@app.get("/health")
async def health():

    return {
        "status": "healthy",
        "transcribe_with": TRANSCRIBE_WITH
    }


frontend_dist = Path(__file__).resolve().parent.parent / "frontend" / "dist"
if frontend_dist.exists():
    app.mount(
        "/",
        StaticFiles(directory=frontend_dist, html=True),
        name="frontend",
    )
