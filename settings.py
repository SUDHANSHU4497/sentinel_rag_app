"""All settings of the fraud-explain API, read from .env (copy .env.example). No key is written in the code."""
import os

from dotenv import load_dotenv

load_dotenv()  # reads .env next to the scripts, if there is one


def env(name, default=""):
    """Read one setting, with surrounding quotes and spaces removed (Windows .env files often have them)."""
    return os.getenv(name, default).strip().strip('"').strip("'")


# ---------- where the SENTINEL tables are (only the load scripts need this) ----------
DATA_PATH = env("DATA_PATH", r"C:\Users\sudha\Downloads\Sentinel project data\sentinel_data\tables")

# ---------- transactions + features: "mongodb" (task 1) or "supabase" (Project Work 5) ----------
STORE = env("STORE", "mongodb").lower()
MONGODB_URI = env("MONGODB_URI", "mongodb://localhost:27017")
MONGODB_DB = env("MONGODB_DB", "sentinel")
SUPABASE_URL = env("SUPABASE_URL")
SUPABASE_KEY = env("SUPABASE_KEY")
SUPABASE_SCHEMA = env("SUPABASE_SCHEMA", "public")

# ---------- device and customer neighbourhood: Neo4j (task 2) ----------
NEO4J_URI = env("NEO4J_URI", "neo4j://localhost:7687")
NEO4J_USER = env("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = env("NEO4J_PASSWORD", "sentinel123")

# ---------- policy chunks: Qdrant + Gemini Embedding 2 (task 4) ----------
QDRANT_URL = env("QDRANT_URL", "http://localhost:6333")
QDRANT_API_KEY = env("QDRANT_API_KEY") or None
COLLECTION = env("COLLECTION", "sentinel_docs")
EMBED_PROVIDER = env("EMBED_PROVIDER", "euron").lower()   # "euron" or "google"
EMBED_MODEL = env("EMBED_MODEL", "gemini-embedding-2")
EMBED_DIM = 3072                                           # Gemini Embedding 2 full size, same as task 4
EURI_API_KEY = env("EURI_API_KEY")
EURI_BASE_URL = env("EURI_BASE_URL", "https://api.euron.one/api/v1/euri")
GOOGLE_API_KEY = env("GOOGLE_API_KEY")
TOP_K = int(env("TOP_K", "5"))                             # policy chunks sent to the LLM

# ---------- LLM that writes the explanation ----------
LLM_PROVIDER = env("LLM_PROVIDER", "euron").lower()        # "euron" (OpenAI-style gateway) or "google"
LLM_MODEL = env("LLM_MODEL", "gpt-4.1-mini")
LLM_TEMPERATURE = float(env("LLM_TEMPERATURE", "0"))       # 0 = the same answer for the same context

# ---------- service ----------
API_URL = env("API_URL", "http://127.0.0.1:8000")          # used by run_tests.py
OUTPUT_DIR = env("OUTPUT_DIR", "outputs")
