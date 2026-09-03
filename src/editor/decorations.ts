import * as vscode from "vscode";
import type { DiagnosticItem } from "../types/protocol";

/**
 * Editor decoration management for the ReviewX extension.
 * Renders color-coded squiggles under code lines flagged in diagnostic payloads.
 */

/** Map diagnostic severity to VS Code decoration types */
const decorationTypes: Map<string, vscode.TextEditorDecorationType> = new Map();

/** Track which diagnostics are currently rendered per URI */
const activeDecorations: Map<string, Map<string, vscode.DecorationOptions[]>> = new Map();

/**
 * Get or create a decoration type for a given severity
 */
function getDecorationType(severity: string): vscode.TextEditorDecorationType {
  if (!decorationTypes.has(severity)) {
    const color = getSeverityColor(severity);
    decorationTypes.set(
      severity,
      vscode.window.createTextEditorDecorationType({
        textDecoration: `underline wavy ${color}`,
        overviewRulerColor: color,
        overviewRulerLane: vscode.OverviewRulerLane.Right,
        light: { textDecoration: `underline wavy ${color}` },
        dark: { textDecoration: `underline wavy ${color}` }
      })
    );
  }
  return decorationTypes.get(severity)!;
}

/**
 * Get color for a diagnostic severity
 */
function getSeverityColor(severity: string): string {
  switch (severity) {
    case "error":
      return "var(--vscode-problemsErrorIcon-foreground)";
    case "warning":
      return "var(--vscode-problemsWarningIcon-foreground)";
    case "information":
      return "var(--vscode-problemsInfoIcon-foreground)";
    case "hint":
      return "var(--vscode-editorHint-foreground)";
    default:
      return "var(--vscode-problemsInfoIcon-foreground)";
  }
}

/**
 * Render decorations for a list of diagnostics in a text editor
 */
export function renderDecorations(
  editor: vscode.TextEditor,
  diagnostics: DiagnosticItem[]
): void {
  const uri = editor.document.uri.toString();

  // Clear previous decorations for this URI
  clearDecorations(editor);

  if (!activeDecorations.has(uri)) {
    activeDecorations.set(uri, new Map());
  }

  const uriDecorations = activeDecorations.get(uri)!;

  for (const diagnostic of diagnostics) {
    const severity = diagnostic.severity || "information";
    if (!uriDecorations.has(severity)) {
      uriDecorations.set(severity, []);
    }

    const range = new vscode.Range(
      diagnostic.range.start.line,
      diagnostic.range.start.character,
      diagnostic.range.end.line,
      diagnostic.range.end.character
    );

    uriDecorations.get(severity)!.push({
      range,
      hoverMessage: new vscode.MarkdownString(
        `**${diagnostic.message}**\n\n${diagnostic.recommendation || ""}`
      )
    });
  }

  // Apply all decorations
  for (const [severity, decorations] of uriDecorations.entries()) {
    const decorationType = getDecorationType(severity);
    editor.setDecorations(decorationType, decorations);
  }
}

/**
 * Clear all decorations for a text editor
 */
export function clearDecorations(editor: vscode.TextEditor): void {
  const uri = editor.document.uri.toString();

  if (activeDecorations.has(uri)) {
    const uriDecorations = activeDecorations.get(uri)!;
    for (const [severity, _] of uriDecorations.entries()) {
      const decorationType = getDecorationType(severity);
      editor.setDecorations(decorationType, []);
    }
    activeDecorations.delete(uri);
  }
}

/**
 * Trigger a background scan of the active editor
 */
export function triggerBackgroundScan(editor: vscode.TextEditor): void {
  console.log(`Triggering background scan for: ${editor.document.uri.toString()}`);
  // Scan logic would be implemented here
  // For now, this is a placeholder
}

/**
 * Register listeners for active editor changes
 */
export function registerEditorChangeListeners(): vscode.Disposable {
  return vscode.window.onDidChangeActiveTextEditor((editor) => {
    if (editor) {
      triggerBackgroundScan(editor);
    }
  });
}

/**
 * Dispose all decoration types
 */
export function disposeAllDecorations(): void {
  for (const decorationType of decorationTypes.values()) {
    decorationType.dispose();
  }
  decorationTypes.clear();
  activeDecorations.clear();
}