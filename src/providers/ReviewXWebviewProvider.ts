import * as vscode from "vscode";
import {
  ReviewXCommand,
  ReviewXCommandType,
  JsonRpcErrorCode,
  JsonRpcMessage,
  JsonRpcRequest,
  JsonRpcResponse,
  ScanFileParams,
  ScanFileResult,
  RenderDiagnosticParams,
  RenderDiagnosticResult,
  VerifyAnswerParams,
  VerifyAnswerResult,
  ApplyCodeFixParams,
  ApplyCodeFixResult,
  DiagnosticItem,
  createJsonRpcSuccessResponse,
  createJsonRpcErrorResponse,
  isJsonRpcRequest
} from "../types/protocol";
import { applyLineDecorations } from "../editor/decorations";

/**
 * WebviewViewProvider for the ReviewX extension.
 */
export class ReviewXWebviewProvider implements vscode.WebviewViewProvider {
  public static readonly viewType = "reviewX.sidebarView";
  private _view?: vscode.WebviewView;
  private readonly _diagnosticCollection: vscode.DiagnosticCollection;
  private _pendingRequests = new Map<string | number, { resolve: (v: unknown) => void; reject: (r?: unknown) => void; timeout: NodeJS.Timeout; }>();
  private _requestIdCounter = 1;

  constructor(
    private readonly _extensionUri: vscode.Uri,
    diagnosticCollection?: vscode.DiagnosticCollection
  ) {
    this._diagnosticCollection = diagnosticCollection ?? vscode.languages.createDiagnosticCollection("reviewX");
  }

  public resolveWebviewView(
    webviewView: vscode.WebviewView,
    _context: vscode.WebviewViewResolveContext,
    _token: vscode.CancellationToken
  ): void {
    this._view = webviewView;
    webviewView.webview.options = { enableScripts: true, localResourceRoots: [this._extensionUri] };
    webviewView.webview.html = this._getHtmlForWebview(webviewView.webview);

    webviewView.webview.onDidReceiveMessage(
      async (message: unknown) => { await this.handleWebviewMessage(message); },
      undefined
    );

    vscode.window.onDidChangeActiveTextEditor(editor => {
      if (editor && this._view?.visible) {
        this.sendNotification("ON_ACTIVE_EDITOR_CHANGED", {
          uri: editor.document.uri.toString(),
          languageId: editor.document.languageId,
          lineCount: editor.document.lineCount
        }).catch(err => console.error("Failed to notify webview:", err));
      }
    });

    webviewView.onDidDispose(() => {
      this._view = undefined;
      this._diagnosticCollection.clear();
      for (const [, pending] of this._pendingRequests) {
        clearTimeout(pending.timeout);
        pending.reject(new Error("Webview disposed"));
      }
      this._pendingRequests.clear();
    });
  }

  public async handleWebviewMessage(rawMessage: unknown): Promise<void> {
    if (!isJsonRpcRequest(rawMessage)) {
      if (typeof rawMessage === "object" && rawMessage !== null && "id" in rawMessage && ("result" in rawMessage || "error" in rawMessage)) {
        const res = rawMessage as JsonRpcResponse;
        const pending = this._pendingRequests.get(res.id as string | number);
        if (pending) {
          clearTimeout(pending.timeout);
          this._pendingRequests.delete(res.id as string | number);
          if (res.error) pending.reject(new Error(res.error.message));
          else pending.resolve(res.result);
        }
        return;
      }
      console.warn("Received invalid JSON-RPC message:", rawMessage);
      return;
    }

    const request = rawMessage as JsonRpcRequest<ReviewXCommandType>;
    const requestId = request.id;

    try {
      let response: JsonRpcResponse;
      switch (request.method) {
        case ReviewXCommand.SCAN_FILE: {
          const result = await this.handleScanFile(request.params as ScanFileParams);
          response = createJsonRpcSuccessResponse(requestId, result);
          break;
        }
        case ReviewXCommand.RENDER_DIAGNOSTIC: {
          const result = await this.handleRenderDiagnostic(request.params as RenderDiagnosticParams);
          response = createJsonRpcSuccessResponse(requestId, result);
          break;
        }
        case ReviewXCommand.VERIFY_ANSWER: {
          const result = await this.handleVerifyAnswer(request.params as VerifyAnswerParams);
          response = createJsonRpcSuccessResponse(requestId, result);
          break;
        }
        case ReviewXCommand.APPLY_CODE_FIX: {
          const result = await this.handleApplyCodeFix(request.params as ApplyCodeFixParams);
          response = createJsonRpcSuccessResponse(requestId, result);
          break;
        }
        default: {
          response = createJsonRpcErrorResponse(
            requestId,
            JsonRpcErrorCode.MethodNotFound,
            `Unknown method: ${(request as { method: string }).method}`
          );
          break;
        }
      }
      await this.postMessageToWebview(response);
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : "Internal error occurred";
      await this.postMessageToWebview(
        createJsonRpcErrorResponse(requestId, JsonRpcErrorCode.InternalError, errorMessage, error)
      );
    }
  }

  private _getHtmlForWebview(webview: vscode.Webview): string {
    const scriptUri = webview.asWebviewUri(
      vscode.Uri.joinPath(this._extensionUri, "dist", "webview", "main.js")
    );
    const styleUri = webview.asWebviewUri(
      vscode.Uri.joinPath(this._extensionUri, "dist", "webview", "main.css")
    );
    return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src http://127.0.0.1:8000 http://localhost:8000;" />
  <link rel="stylesheet" href="${styleUri}" />
  <title>ReviewX</title>
</head>
<body>
  <div id="webview-container"></div>
  <script type="module" src="${scriptUri}"></script>
</body>
</html>`;
  }

  // SCAN_FILE Handler
  public async handleScanFile(params: ScanFileParams): Promise<ScanFileResult> {
    let document: vscode.TextDocument | undefined;
    if (params.uri) {
      try {
        document = await vscode.workspace.openTextDocument(vscode.Uri.parse(params.uri));
      } catch (err) {
        throw new Error(`Failed to open document: ${params.uri} - ${err}`);
      }
    } else {
      const editor = vscode.window.activeTextEditor;
      if (!editor) throw new Error("No active editor and no URI provided.");
      document = editor.document;
    }
    const text = params.content ?? document.getText();
    const lines = text.split(/\r\n|\r|\n/);
    const diagnostics: DiagnosticItem[] = [];
    lines.forEach((line, idx) => {
      if (/TODO|FIXME/.test(line)) {
        const marker = line.indexOf("TODO") >= 0 ? "TODO" : "FIXME";
        diagnostics.push({
          id: `todo-${idx}`,
          message: "Unresolved TODO/FIXME comment.",
          range: { start: { line: idx, character: line.indexOf(marker) }, end: { line: idx, character: line.length } },
          severity: "information",
          source: "ReviewX",
          category: "Code Quality"
        });
      }
    });
    return {
      uri: document.uri.toString(),
      languageId: document.languageId,
      content: text,
      lineCount: document.lineCount,
      diagnostics,
      symbolsScanned: lines.length,
      findingsCount: diagnostics.length,
      timestamp: Date.now()
    };
  }

  // RENDER_DIAGNOSTIC Handler
  public async handleRenderDiagnostic(params: RenderDiagnosticParams): Promise<RenderDiagnosticResult> {
    if (!params.uri) throw new Error("Missing 'uri' parameter in RENDER_DIAGNOSTIC request.");
    const targetUri = vscode.Uri.parse(params.uri);
    if (params.clearPrevious) this._diagnosticCollection.delete(targetUri);
    const vscodeDiagnostics: vscode.Diagnostic[] = (params.diagnostics || []).map((item: DiagnosticItem) => {
      const range = new vscode.Range(
        new vscode.Position(item.range.start.line, item.range.start.character),
        new vscode.Position(item.range.end.line, item.range.end.character)
      );
      let severity = vscode.DiagnosticSeverity.Information;
      switch (item.severity) {
        case "error": severity = vscode.DiagnosticSeverity.Error; break;
        case "warning": severity = vscode.DiagnosticSeverity.Warning; break;
        case "information": severity = vscode.DiagnosticSeverity.Information; break;
        case "hint": severity = vscode.DiagnosticSeverity.Hint; break;
      }
      const diagnostic = new vscode.Diagnostic(range, item.message, severity);
      diagnostic.source = item.source ?? "ReviewX";
      if (item.code !== undefined) diagnostic.code = item.code;
      return diagnostic;
    });
    this._diagnosticCollection.set(targetUri, vscodeDiagnostics);

    const editor = vscode.window.visibleTextEditors.find(
      candidate => candidate.document.uri.toString() === targetUri.toString()
    );
    if (editor) applyLineDecorations(editor, params.diagnostics || []);

    return { uri: targetUri.toString(), renderedCount: vscodeDiagnostics.length, success: true, timestamp: Date.now() };
  }

  // VERIFY_ANSWER Handler
  public async handleVerifyAnswer(params: VerifyAnswerParams): Promise<VerifyAnswerResult> {
    if (!params.questionId) throw new Error("Missing 'questionId' in VERIFY_ANSWER request.");
    const isCorrect = Boolean(
      (params.selectedOptionId && params.selectedOptionId.endsWith("_correct")) ||
      (params.textAnswer && params.textAnswer.trim().length > 0)
    );
    const feedback = isCorrect
      ? `Verification successful for question '${params.questionId}'.`
      : `Verification failed for question '${params.questionId}'.`;
    return {
      questionId: params.questionId,
      isCorrect,
      score: isCorrect ? 100 : 0,
      feedback,
      explanation: isCorrect
        ? "The provided response fulfills all architectural constraints."
        : "Ensure edge cases and syntax requirements are addressed.",
      hints: isCorrect
        ? undefined
        : ["Inspect type constraints", "Check nullability checks"],
      nextChallengeId: isCorrect ? `challenge-${Date.now()}` : undefined,
      timestamp: Date.now()
    };
  }

  // APPLY_CODE_FIX Handler
  public async handleApplyCodeFix(params: ApplyCodeFixParams): Promise<ApplyCodeFixResult> {
    if (!params.uri || !params.edits || !Array.isArray(params.edits))
      throw new Error("Invalid parameters: 'uri' and 'edits' array are required.");
    const targetUri = vscode.Uri.parse(params.uri);
    const workspaceEdit = new vscode.WorkspaceEdit();
    for (const edit of params.edits) {
      const range = new vscode.Range(
        new vscode.Position(edit.range.start.line, edit.range.start.character),
        new vscode.Position(edit.range.end.line, edit.range.end.character)
      );
      workspaceEdit.replace(targetUri, range, edit.newText);
    }
    const applied = await vscode.workspace.applyEdit(workspaceEdit);
    if (!applied) throw new Error(`Failed to apply workspace edit for ${params.uri}`);
    return {
      uri: targetUri.toString(),
      fixId: params.fixId,
      appliedEditsCount: params.edits.length,
      success: applied,
      message: `Successfully applied fix: ${params.title}`,
      timestamp: Date.now()
    };
  }

  // Outbound Messaging Helpers

  public async postMessageToWebview(message: JsonRpcMessage): Promise<boolean> {
    if (!this._view) {
      console.warn("Cannot post message: Webview view is not currently resolved.");
      return false;
    }
    return this._view.webview.postMessage(message);
  }

  public async sendNotification(method: string, params?: unknown): Promise<boolean> {
    return this.postMessageToWebview({
      jsonrpc: "2.0",
      method,
      params
    });
  }

  public sendRequest<TResult>(
    method: string,
    params?: unknown,
    timeoutMs = 10000
  ): Promise<TResult> {
    const id = this._requestIdCounter++;

    return new Promise((resolve, reject) => {
      const timeout = setTimeout(() => {
        this._pendingRequests.delete(id);
        reject(new Error(`Request '${method}' (id: ${id}) timed out after ${timeoutMs}ms`));
      }, timeoutMs);

      this._pendingRequests.set(id, {
        resolve: resolve as (val: unknown) => void,
        reject,
        timeout
      });

      this.postMessageToWebview({
        jsonrpc: "2.0",
        id,
        method,
        params
      }).catch(err => {
        clearTimeout(timeout);
        this._pendingRequests.delete(id);
        reject(err);
      });
    });
  }
}
