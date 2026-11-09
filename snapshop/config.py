"""Central settings, read from .env so the demo can be reconfigured without code changes."""
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
# Vision model on Groq (reads the photo) and text model (reasoning / verdict).
GROQ_VISION_MODEL = os.getenv("GROQ_VISION_MODEL", "qwen/qwen3.8-27b")
GROQ_TEXT_MODEL = os.getenv("GROQ_TEXT_MODEL", "openai/gpt-oss-120b")

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
# gemma3:4b understands images AND text, so one small download covers offline mode.
OLLAMA_VISION_MODEL = os.getenv("OLLAMA_VISION_MODEL", "gemma3:4b")
OLLAMA_TEXT_MODEL = os.getenv("OLLAMA_TEXT_MODEL", "gemma3:4b")

SCREENSHOT_DIR = ROOT / "screenshots"
SCREENSHOT_DIR.mkdir(exist_ok=True)

PAGE_TIMEOUT_MS = int(os.getenv("PAGE_TIMEOUT_MS", "25000"))
