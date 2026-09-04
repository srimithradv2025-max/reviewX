import os
import chromadb
from dotenv import load_dotenv

load_dotenv()

CHROMA_PATH = os.getenv("CHROMA_DB_DIR", "./data/chroma_db")

STANDARDS_DATA = [
    {
        "id": "SEC-KEY-01",
        "title": "OWASP A07: Identification and Authentication Failures - Hardcoded Credentials",
        "text": "Hardcoding active API keys, passwords, or private encryption keys directly inside source code exposes credentials to anyone with read access to the repository. Secrets must be stored in environment variables or external secret managers.",
        "category": "Security"
    },
    {
        "id": "SEC-INJ-01",
        "title": "OWASP A03: Injection - Unsanitized SQL/Command Execution",
        "text": "Constructing database queries or system commands using string concatenation with raw user input allows injection attacks. Always use parameterized queries or input sanitization functions.",
        "category": "Security"
    },
    {
        "id": "HW-LOOP-01",
        "title": "Hardware Safety Standard: Unconstrained CPU Execution Loops",
        "text": "Infinite execution loops without yield, sleep, or watchdog reset mechanisms can freeze microcontrollers or cause physical actuator lockup. Always include watchdog timeout checks or delay loops.",
        "category": "Hardware Safety"
    },
    {
        "id": "HW-MEM-01",
        "title": "System Safety: Direct Unbounded Hardware Memory Address Writes",
        "text": "Writing values directly to arbitrary hardware memory addresses without boundary checking can corrupt system registers, cause kernel panic, or command uncalibrated physical hardware motion.",
        "category": "Hardware Safety"
    }
]

def ingest_standards():
    print(f"Initializing ChromaDB vector store at {CHROMA_PATH}...")
    
    # Ensure data directory exists
    os.makedirs(os.path.dirname(CHROMA_PATH), exist_ok=True)
    
    client = chromadb.PersistentClient(path=CHROMA_PATH)
    collection = client.get_or_create_collection(name="expertise_rules")

    ids = [item["id"] for item in STANDARDS_DATA]
    documents = [item["text"] for item in STANDARDS_DATA]
    metadatas = [{"title": item["title"], "category": item["category"]} for item in STANDARDS_DATA]

    collection.upsert(ids=ids, documents=documents, metadatas=metadatas)
    print(f"Successfully ingested {len(ids)} authoritative standards into ChromaDB!")

if __name__ == "__main__":
    ingest_standards()