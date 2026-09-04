import type { DiagnosticItem, TextEditItem } from "../../types/protocol";

const HASH_COMMENT_LANGUAGES = new Set([
  "python",
  "py",
  "shellscript",
  "bash",
  "sh",
  "yaml",
  "ruby",
  "makefile",
  "dockerfile"
]);

function commentPrefix(languageId?: string): string {
  return HASH_COMMENT_LANGUAGES.has((languageId ?? "python").toLowerCase()) ? "#" : "//";
}

function leadingIndent(snippet?: string): string {
  return /^[ \t]*/.exec(snippet ?? "")?.[0] ?? "";
}

export function hasConcreteFix(diagnostic: DiagnosticItem): boolean {
  return Boolean(diagnostic.fix?.newText);
}

/**
 * Edits for a verified finding.
 *
 * A diagnostic carrying a `fix` replaces its own range with real source.
 * Otherwise the remediation is inserted above the offending line as
 * comments — the scanner reports point ranges and prose guidance, which
 * must never be written into the file as executable code.
 */
export function buildFixEdits(
  diagnostic: DiagnosticItem,
  languageId?: string
): TextEditItem[] | null {
  const fix = diagnostic.fix;
  if (fix?.newText) {
    return [{ range: fix.range, newText: fix.newText }];
  }

  const recommendation = diagnostic.recommendation?.trim();
  if (!recommendation) return null;

  const indent = leadingIndent(diagnostic.snippet);
  const prefix = commentPrefix(languageId);
  const lines = recommendation.split("\n").map(line => line.trim());
  const body = lines
    .map((line, index) =>
      index === 0
        ? `${indent}${prefix} ReviewX: ${line}`
        : `${indent}${prefix} ${line}`
    )
    .join("\n");

  const line = diagnostic.range.start.line;
  return [
    {
      range: { start: { line, character: 0 }, end: { line, character: 0 } },
      newText: `${body}\n`
    }
  ];
}
