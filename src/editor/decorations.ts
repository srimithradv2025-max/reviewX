import * as vscode from 'vscode';

const errorDecoration = vscode.window.createTextEditorDecorationType({
  textDecoration: '3px solid #ef4444',
  overviewRulerColor: '#ef4444',
  overviewRulerLane: vscode.OverviewRulerLane.Right,
});

const warningDecoration = vscode.window.createTextEditorDecorationType({
  textDecoration: '3px dashed #f59e0b',
  overviewRulerColor: '#f59e0b',
  overviewRulerLane: vscode.OverviewRulerLane.Right,
});

export function applyLineDecorations(editor: vscode.TextEditor, defects: any[]) {
  const errorRanges: vscode.Range[] = [];
  const warningRanges: vscode.Range[] = [];

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

  editor.setDecorations(errorDecoration, errorRanges);
  editor.setDecorations(warningDecoration, warningRanges);
}