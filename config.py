import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Base directories
PROJECT_ROOT = Path(__file__).resolve().parent
WORKSPACE_DIR = Path(os.getenv("WORKSPACE_DIR", "/Users/anooptiwari/Downloads")).resolve()

# Database path for thread persistence
DB_PATH = PROJECT_ROOT / "research_history.db"

# LLM Model Configuration
MODEL_NAME = os.getenv("MODEL_NAME", "google_genai:gemini-3.5-flash")

# Security configurations
FORBIDDEN_TOKENS = ["sudo", "shutdown", "reboot", "mkfs", "dd", "format", "chown", "chmod", "mv"]
SENSITIVE_PATTERNS = [
    r"\.ssh", r"\.aws", r"\.git", r"\.env", r"history", r"\.bash_profile",
    r"\.bashrc", r"\.zshrc", r"id_rsa", r"id_dsa"
]

# Ensure workspace directory exists
WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)
