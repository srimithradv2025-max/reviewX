import * as vscode from 'vscode';
import axios from 'axios';
import { applyLineDecorations } from './editor/decorations';

export function activate(context: vscode.ExtensionContext) {
  const provider = new SidebarProvider(context.extensionUri);
  context.subscriptions.push(
    vscode.window.registerWebviewViewProvider('expertiseBridge.sidebarView', provider)
  );

  vscode.workspace.onDidChangeTextDocument(async (event) => {
    const editor = vscode.window.activeTextEditor;
    if (editor && event.document === editor.document) {
      try {
        const response = await axios.post('http://127.0.0.1:8000/api/v1/scan', {
          code_snippet: event.document.getText(),
          language: event.document.languageId
        });
        if (response.data.defects) {
          applyLineDecorations(editor, response.data.defects);
          provider.sendMessageToWebview({
            type: 'RENDER_DIAGNOSTIC',
            payload: response.data.defects
          });
        }
      } catch (err) {
        console.warn('ReviewX Backend offline at http://127.0.0.1:8000');
      }
    }
  });
}

class SidebarProvider implements vscode.WebviewViewProvider {
  private _view?: vscode.WebviewView;

  constructor(private readonly _extensionUri: vscode.Uri) {}

  resolveWebviewView(webviewView: vscode.WebviewView) {
    this._view = webviewView;
    webviewView.webview.options = { enableScripts: true };
    webviewView.webview.html = this._getHtmlForWebview();

    webviewView.webview.onDidReceiveMessage(async (message) => {
      if (message.type === 'APPLY_CODE_FIX') {
        const editor = vscode.window.activeTextEditor;
        if (editor) {
          const fullRange = new vscode.Range(
            editor.document.positionAt(0),
            editor.document.positionAt(editor.document.getText().length)
          );
          await editor.edit((editBuilder) => editBuilder.replace(fullRange, message.payload.fixCode));
          vscode.window.showInformationMessage('ReviewX: Verified code fix applied to editor!');
        }
      }
    });
  }

  public sendMessageToWebview(msg: any) {
    if (this._view) {
      this._view.webview.postMessage(msg);
    }
  }

  private _getHtmlForWebview(): string {
    return `<!DOCTYPE html>
      <html>
      <head><meta charset="UTF-8"><title>ReviewX</title></head>
      <body style="background-color: var(--vscode-editor-background); color: var(--vscode-editor-foreground); padding: 12px; font-family: sans-serif;">
        <div id="root">
          <h3 style="font-size: 14px; margin-bottom: 4px;">ExpertiseBridge ReviewX</h3>
          <p style="font-size: 11px; color: #94a3b8;">Active code verification and RAG domain guardrails running.</p>
        </div>
      </body>
      </html>`;
  }
}