import ast
import re

def parse_code_ast(code_snippet: str, language: str = "python") -> list:
    """Parses source code for security flaws using Python's AST module and regex heuristics."""
    defects = []
    
    # 1. Regex scan for hardcoded credentials / secrets
    key_pattern = r"(api_key|secret|password)\s*=\s*['\"](?!\$\{)[A-Za-z0-9_\-]{16,}['\"]"
    for i, line in enumerate(code_snippet.splitlines(), start=1):
        if re.search(key_pattern, line, re.IGNORECASE):
            defects.append({
                "id": f"DEF-{i}",
                "line": i,
                "rule_id": "SEC-KEY-01",
                "severity": "error",
                "message": "Hardcoded credential detected directly in source code.",
                "plain_explanation": "You stored an active secret or API key directly inside code, making it visible to anyone with repository access.",
                "grounding_source": "OWASP A07:2021 - Identification & Authentication Failures",
                "suggested_fix": "# Store credentials in environment variables\nimport os\napi_key = os.getenv('API_KEY')"
            })

    # 2. AST parsing for Python-specific vulnerabilities
    if language.lower() == "python":
        try:
            tree = ast.parse(code_snippet)
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "eval":
                    defects.append({
                        "id": f"DEF-{node.lineno}",
                        "line": node.lineno,
                        "rule_id": "SEC-INJ-01",
                        "severity": "error",
                        "message": "Dangerous dynamic execution method eval() used.",
                        "plain_explanation": "Using eval() executes arbitrary text input as code, allowing attackers to manipulate internal state.",
                        "grounding_source": "OWASP A03:2021 - Injection Flaws",
                        "suggested_fix": "# Replace eval with safe literal parsing\nimport ast\ndata = ast.literal_eval(user_input)"
                    })
        except SyntaxError:
            pass

    return defects