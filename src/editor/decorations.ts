import * as vscode from "vscode";
import { DiagnosticItem } from "../types/protocol";

const warningDecoration = vscode.window.createTextEditorDecorationType({
  textDecoration: "underline 3px dashed #f59e0b",
  overviewRulerColor: "#f59e0b",
  overviewRulerLane: vscode.OverviewRulerLane.Right
});

const errorDecoration = vscode.window.createTextEditorDecorationType({
  textDecoration: "underline 3px solid #ef4444",
  overviewRulerColor: "#ef4444",
  overviewRulerLane: vscode.OverviewRulerLane.Right
});

export function applyLineDecorations(
  editor: vscode.TextEditor,
  diagnostics: DiagnosticItem[]
): void {
  const warningRanges: vscode.Range[] = [];
  const errorRanges: vscode.Range[] = [];
  const lastLine = editor.document.lineCount - 1;

  diagnostics.forEach(diagnostic => {
    const lineIndex = Math.min(Math.max(0, diagnostic.range.start.line), lastLine);
    const line = editor.document.lineAt(lineIndex);
    const range = new vscode.Range(lineIndex, 0, lineIndex, line.text.length);

    if (diagnostic.severity === "error") {
      errorRanges.push(range);
    } else {
      warningRanges.push(range);
    }
  });

  editor.setDecorations(warningDecoration, warningRanges);
  editor.setDecorations(errorDecoration, errorRanges);
}
