import re

def verify_domain_interlocks(code_snippet: str, language: str) -> dict:
    """Evaluates physical and system domain safety rules using deterministic pattern matching."""
    
    # Check 1: Direct Memory Write / Pointer Access
    raw_memory_pattern = r"\*\(\s*volatile\s+uint32_t\s*\*\)\s*0x[0-9a-fA-F]+"
    if re.search(raw_memory_pattern, code_snippet):
        return {
            "safety_breach": True,
            "interlock_id": "HW-MEM-01",
            "message": "Physical Safety Risk: Direct raw memory register write detected without hardware abstraction layer."
        }

    # Check 2: Destructive System Operations
    destructive_cmds = [r"rm\s+-rf", r"os\.system\s*\(\s*[\"']format", r"subprocess\.call\(.*shell=True"]
    for pattern in destructive_cmds:
        if re.search(pattern, code_snippet, re.IGNORECASE):
            return {
                "safety_breach": True,
                "interlock_id": "SYS-CMD-01",
                "message": "System Risk: Destructive system shell execution detected."
            }

    # Check 3: Infinite loop without sleep/yield
    if "while(true)" in code_snippet.lower().replace(" ", "") and "sleep" not in code_snippet.lower():
        return {
            "safety_breach": True,
            "interlock_id": "HW-LOOP-01",
            "message": "Hardware Hazard: Infinite execution loop without sleep or watchdog delay."
        }

    return {"safety_breach": False}