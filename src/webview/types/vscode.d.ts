/**
 * Global type declarations for the ReviewX Webview.
 * Provides types for the VS Code Webview API injected at runtime.
 */

declare global {
  /**
   * VS Code Webview API injected into the webview at runtime.
   * Provides the `acquireVsCodeApi()` function and a `vscode` global object.
   */
  interface VsCodeWebviewApi {
    /**
     * Post a message to the Extension Host. Returns a boolean indicating
     * whether the message was successfully queued for delivery.
     */
    postMessage(message: unknown): Promise<boolean>;

    /**
     * Set persistent state for the webview. Survives across webview reloads.
     */
    setState?(state: Record<string, unknown>): void;

    /**
     * Get persistent state for the webview.
     */
    getState?(): Record<string, unknown> | undefined;
  }

  /**
   * Acquire the VS Code Webview API singleton.
   * This is injected by VS Code into the webview's global scope.
   */
  function acquireVsCodeApi(): VsCodeWebviewApi | undefined;

  /**
   * Optional window.vscode fallback for older VS Code versions.
   */
  interface Window {
    vscode?: VsCodeWebviewApi;
  }
}

export {};
