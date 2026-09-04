from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from backend.app.services.ast_parser import parse_code_ast
from ai.guardrails.domain_interlocks import verify_domain_interlocks

app = FastAPI(title="ReviewX / ExpertiseBridge Core API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ScanRequest(BaseModel):
    code_snippet: str
    language: str = "python"

@app.post("/api/v1/scan")
async def scan_code(payload: ScanRequest):
    # 1. Run Physical & System Domain Interlocks
    interlock = verify_domain_interlocks(payload.code_snippet, payload.language)
    if interlock["safety_breach"]:
        return {
            "status": "BLOCKED",
            "defects": [{
                "id": "INT-001",
                "line": 1,
                "severity": "error",
                "message": interlock["message"],
                "rule_id": interlock["interlock_id"],
                "plain_explanation": interlock["message"],
                "grounding_source": "Hardware Safety Domain Interlock",
                "suggested_fix": "# Add boundary limits and yield delays"
            }]
        }

    # 2. Run AST Static Analyzer
    defects = parse_code_ast(payload.code_snippet, payload.language)
    return {"status": "COMPLETED", "defects": defects}