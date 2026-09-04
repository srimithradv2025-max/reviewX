import * as vscode from "vscode";
import { ReviewXWebviewProvider } from "./providers/ReviewXWebviewProvider";
import { ReviewXCommand } from "./types/protocol";

export function activate(context: vscode.ExtensionContext): void {
  const diagnosticCollection = vscode.languages.createDiagnosticCollection("reviewX");
  const provider = new ReviewXWebviewProvider(context.extensionUri, diagnosticCollection);

  context.subscriptions.push(
    diagnosticCollection,
    vscode.window.registerWebviewViewProvider(ReviewXWebviewProvider.viewType, provider),
    vscode.commands.registerCommand("reviewX.refreshView", async () => {
      await provider.sendNotification("ON_REFRESH_VIEW", { timestamp: Date.now() });
    }),
    vscode.commands.registerCommand("reviewX.scanActiveFile", async () => {
      const editor = vscode.window.activeTextEditor;
      if (!editor) {
        vscode.window.showWarningMessage("ReviewX: open a file to scan.");
        return;
      }
      await provider.sendNotification(ReviewXCommand.SCAN_FILE, {
        uri: editor.document.uri.toString(),
        content: editor.document.getText(),
        languageId: editor.document.languageId
      });
    })
  );
}

export function deactivate(): void {
  // Disposables are cleaned up through the extension context subscriptions.
}
