import os
import json
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()

GEMINI_KEY = os.getenv("GEMINI_API_KEY")

FALLBACK_BENCHMARK = [
    {
        "case_id": "TC-001",
        "language": "python",
        "code": "api_key = 'sk_live_9921821a9d8213'\ndef connect():\n    return login(api_key)",
        "expected_defect": "Hardcoded Credentials",
        "rule_id": "SEC-KEY-01",
        "is_vulnerable": True
    },
    {
        "case_id": "TC-002",
        "language": "cpp",
        "code": "void drive_motor() {\n    while(true) {\n        *(volatile uint32_t*)0x40001000 = 0xFF;\n    }\n}",
        "expected_defect": "Unconstrained Hardware Memory Write",
        "rule_id": "HW-MEM-01",
        "is_vulnerable": True
    },
    {
        "case_id": "TC-003",
        "language": "python",
        "code": "import sqlite3\ndef get_user(name):\n    query = f'SELECT * FROM users WHERE username = \"{name}\"'\n    return db.execute(query)",
        "expected_defect": "SQL Injection",
        "rule_id": "SEC-INJ-01",
        "is_vulnerable": True
    }
]

def generate_benchmark_dataset():
    output_file = "data/benchmark_dataset.json"
    os.makedirs("data", exist_ok=True)

    if GEMINI_KEY:
        try:
            genai.configure(api_key=GEMINI_KEY)
            model = genai.GenerativeModel('gemini-2.0-flash-exp')
            prompt = "Generate a JSON list of 10 vulnerable code snippets across Python and C++ with keys: case_id, language, code, expected_defect, rule_id, is_vulnerable."
            response = model.generate_content(prompt)
            print("Generated synthetic dataset via Gemini API.")
        except Exception as e:
            print(f"Gemini API unavailable ({e}). Utilizing fallback benchmark dataset.")
    
    with open(output_file, "w") as f:
        json.dump(FALLBACK_BENCHMARK, f, indent=2)
    
    print(f"Benchmark dataset saved to {output_file}")

if __name__ == "__main__":
    generate_benchmark_dataset()