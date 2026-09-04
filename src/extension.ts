import * as vscode from 'vscode';
import axios from 'axios';
import { applyLineDecorations } from './editor/decorations';

interface ScanDefect {
  id: string;
  line: number;
  message: string;
  rule_id: string;
  severity: 'warning' | 'error';
  plain_explanation?: string;
  grounding_source?: string;
  suggested_fix?: string;
}

interface ScanResponseData {
  status: string;
  defects?: ScanDefect[];
  reason?: string;
}

interface ApplyFixPayload {
  fixCode: string;
}

interface WebviewIncomingMessage {
  type: string;
  payload?: ApplyFixPayload;
}

export function activate(context: vscode.ExtensionContext): void {
  const provider = new SidebarProvider(context.extensionUri);
  context.subscriptions.push(
    vscode.window.registerWebviewViewProvider('reviewX.sidebarView', provider)
  );

  const docChangeListener = vscode.workspace.onDidChangeTextDocument(async (event: vscode.TextDocumentChangeEvent) => {
    const editor = vscode.window.activeTextEditor;
    if (editor && event.document === editor.document) {
      try {
        const response = await axios.post<ScanResponseData>('http://127.0.0.1:8000/api/v1/scan', {
          code_snippet: event.document.getText(),
          language: event.document.languageId
        });
        if (response.data && Array.isArray(response.data.defects)) {
          applyLineDecorations(editor, response.data.defects);
          provider.sendMessageToWebview({
            type: 'RENDER_DIAGNOSTIC',
            payload: response.data.defects
          });
        }
      } catch (err: unknown) {
        console.warn('ReviewX Backend offline at http://127.0.0.1:8000', err);
      }
    }
  });

  context.subscriptions.push(docChangeListener);
}

export function deactivate(): void {
  // Clean up extension resources
}

class SidebarProvider implements vscode.WebviewViewProvider {
  private _view?: vscode.WebviewView;

  constructor(private readonly _extensionUri: vscode.Uri) {}

  public resolveWebviewView(
    webviewView: vscode.WebviewView,
    _context: vscode.WebviewViewResolveContext,
    _token: vscode.CancellationToken
  ): void {
    this._view = webviewView;

    webviewView.webview.options = {
      enableScripts: true,
      localResourceRoots: [this._extensionUri]
    };

    webviewView.webview.html = this._getHtmlForWebview(webviewView.webview);

    webviewView.webview.onDidReceiveMessage(async (message: WebviewIncomingMessage) => {
      if (message.type === 'APPLY_CODE_FIX' && message.payload?.fixCode) {
        const editor = vscode.window.activeTextEditor;
        if (editor) {
          const fullRange = new vscode.Range(
            editor.document.positionAt(0),
            editor.document.positionAt(editor.document.getText().length)
          );
          const fixCode = message.payload.fixCode;
          await editor.edit((editBuilder: vscode.TextEditorEdit) => {
            editBuilder.replace(fullRange, fixCode);
          });
          vscode.window.showInformationMessage('ReviewX: Verified code fix applied!');
        }
      }
    });
  }

  public sendMessageToWebview(msg: unknown): void {
    if (this._view) {
      this._view.webview.postMessage(msg);
    }
  }

  private _getHtmlForWebview(webview: vscode.Webview): string {
    const scriptUri = webview.asWebviewUri(
      vscode.Uri.joinPath(this._extensionUri, 'dist', 'webview.js')
    );
    const styleUri = webview.asWebviewUri(
      vscode.Uri.joinPath(this._extensionUri, 'dist', 'style.css')
    );

    return `<!DOCTYPE html>
      <html lang="en">
      <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <link href="${styleUri}" rel="stylesheet">
        <title>ReviewX Assistant</title>
      </head>
      <body style="background-color: var(--vscode-editor-background); color: var(--vscode-editor-foreground); padding: 8px;">
        <div id="root"></div>
        <script src="${scriptUri}"></script>
      </body>
      </html>`;
  }
}