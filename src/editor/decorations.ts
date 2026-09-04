import * as vscode from 'vscode';
import { DiagnosticDefect } from '../types/protocol';

const warningDecoration = vscode.window.createTextEditorDecorationType({
  underlines: '3px dashed #f59e0b',
  overviewRulerColor: '#f59e0b',
  overviewRulerLane: vscode.OverviewRulerLane.Right,
});

const errorDecoration = vscode.window.createTextEditorDecorationType({
  underlines: '3px solid #ef4444',
  overviewRulerColor: '#ef4444',
  overviewRulerLane: vscode.OverviewRulerLane.Right,
});

export function applyLineDecorations(editor: vscode.TextEditor, defects: DiagnosticDefect[]) {
  const warningRanges: vscode.Range[] = [];
  const errorRanges: vscode.Range[] = [];

  defects.forEach((defect) => {
    const lineIndex = Math.max(0, defect.line - 1);
    const line = editor.document.lineAt(lineIndex);
    const range = new vscode.Range(lineIndex, 0, lineIndex, line.text.length);

    if (defect.severity === 'error') {
      errorRanges.push(range);
    } else {
      warningRanges.push(range);
    }
  });

  editor.setDecorations(warningDecoration, warningRanges);
  editor.setDecorations(errorDecoration, errorRanges);
}