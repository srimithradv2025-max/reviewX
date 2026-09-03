"""Smoke test for ``app.services.ast_parser``.

Run from anywhere with the project venv Python:

    C:\\Users\\rindh\\reviewX\\backend\\venv\\Scripts\\python.exe \\\\backend\\\\tests\\\\run_ast_parser_check.py

Prints every finding (rule_id + line + severity + snippet), then validates the
expected findings and clean-sample behaviour, exiting non-zero on failure.
"""

import sys
from pathlib import Path

BACKEND = Path(r"c:\Users\rindh\reviewX\backend")
sys.path.insert(0, str(BACKEND))

from app.services.ast_parser import scan_python  # noqa: E402

SAMPLES = Path(__file__).resolve().parent / "samples"

# (line, rule_id) pairs the scanner must report for vulnerable_sample.py.
EXPECTED_VULNERABLE = {
    (6, "SECRET_API_KEY"),
    (7, "SECRET_JWT"),
    (8, "SECRET_PASSWORD"),
    (9, "SECRET_CONNECTION_STRING"),
    (12, "UNSAFE_SQL"),
    (15, "DANGEROUS_EVAL"),
    (16, "DANGEROUS_EXEC"),
    (19, "UNSAFE_SQL"),
    (23, "UNSAFE_SQL"),
    (26, "MISSING_SAFETY_INTERLOC"),
    (30, "MISSING_SAFETY_INTERLOC"),
    (33, "SECRET_CONNECTION_STRING"),
    (36, "SECRET_API_KEY"),
    (39, "SECRET_PASSWORD"),
}


def main() -> int:
    failures: list[str] = []

    # --- vulnerable sample --------------------------------------------------
    vulnerable = (SAMPLES / "vulnerable_sample.py").read_text(encoding="utf-8")
    findings = scan_python(vulnerable)
    print(f"\n=== Findings in vulnerable_sample.py "
          f"({len(findings)} total) ===")
    for f in findings:
        print(f"  L{f.line:>3}  {f.rule_id:<30} {f.severity:<6} "
              f"{f.message[:72]}")
        print(f"          snippet: {f.snippet[:72]}")

    actual = {(f.line, f.rule_id) for f in findings}
    missing = EXPECTED_VULNERABLE - actual
    if missing:
        failures.append(f"Missing findings: {sorted(missing)}")
    unexpected = actual - EXPECTED_VULNERABLE
    if unexpected:
        failures.append(f"Unexpected findings: {sorted(unexpected)}")

    # Every finding must carry all four required fields.
    for f in findings:
        if not f.rule_id or not f.message or not f.snippet or f.line <= 0:
            failures.append(f"Finding missing a required field: {f}")

    # --- clean sample: no findings expected --------------------------------
    clean = (SAMPLES / "clean_sample.py").read_text(encoding="utf-8")
    clean_findings = scan_python(clean)
    print(f"\n=== Findings in clean_sample.py ({len(clean_findings)} total) ===")
    for f in clean_findings:
        print(f"  L{f.line:>3}  {f.rule_id:<30} {f.severity:<6} {f.message[:72]}")
    if clean_findings:
        failures.append(
            f"clean_sample.py produced {len(clean_findings)} unexpected finding(s)"
        )

    # --- robustness ---------------------------------------------------------
    if scan_python("def broken(:\n") != []:  # unparseable -> []
        failures.append("unparseable source should yield no findings")
    if scan_python("") != []:
        failures.append("empty source should yield no findings")
    if scan_python("x = 1\n") != []:
        failures.append("harmless source should yield no findings")

    print("\n" + ("RESULT: PASS" if not failures else "RESULT: FAIL"))
    for problem in failures:
        print(f"  ! {problem}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())