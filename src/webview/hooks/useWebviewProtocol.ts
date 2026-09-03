import { useState, useEffect, useCallback, useRef } from "react";
import type { JsonRpcMessage } from "../../types/protocol";

/**
 * Hook for Webview Protocol Communication
 * Handles bi-directional JSON-RPC message exchange between Webview and Extension Host
 */

export interface WebviewProtocol {
  sendMessage: (message: JsonRpcMessage) => Promise<boolean>;
  lastMessage: JsonRpcMessage | null;
  error: Error | null;
  isConnected: boolean;
  unsubscribe: () => void;
}

export function useWebviewProtocol(): WebviewProtocol {
  const [lastMessage, setLastMessage] = useState<JsonRpcMessage | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [isConnected, setIsConnected] = useState(false);
  const messageHandlers = useRef<Set<(message: JsonRpcMessage) => void>>(new Set());
  const vscodeApiRef = useRef<VsCodeWebviewApi | null>(null);

  // Initialize VS Code API on mount
  useEffect(() => {
    try {
      // Use acquireVsCodeApi if available, otherwise fall back to window.vscode
      if (typeof acquireVsCodeApi === "function") {
        vscodeApiRef.current = acquireVsCodeApi() ?? null;
      } else if (window.vscode) {
        vscodeApiRef.current = window.vscode;
      }

      if (vscodeApiRef.current) {
        setIsConnected(true);
      }
    } catch (err) {
      setError(err instanceof Error ? err : new Error("Failed to initialize VS Code API"));
    }
  }, []);

  // Set up message listener using VS Code's postMessage API
  useEffect(() => {
    const vscodeApi = vscodeApiRef.current;
    if (!vscodeApi) return;

    const messageListener = (event: MessageEvent) => {
      try {
        const message = event.data as JsonRpcMessage;
        setLastMessage(message);

        // Notify all message handlers
        messageHandlers.current.forEach((handler) => handler(message));
      } catch (err) {
        setError(err instanceof Error ? err : new Error("Invalid message format"));
      }
    };

    window.addEventListener("message", messageListener as EventListener);

    return () => {
      window.removeEventListener("message", messageListener as EventListener);
    };
  }, []);

  // Send message to extension host
  const sendMessage = useCallback(async (message: JsonRpcMessage): Promise<boolean> => {
    try {
      const vscodeApi = vscodeApiRef.current || window.vscode;
      if (!vscodeApi?.postMessage) {
        throw new Error("VS Code API postMessage not available");
      }

      const result = await vscodeApi.postMessage(message);
      return result;
    } catch (err) {
      const error = err instanceof Error ? err : new Error("Failed to send message");
      setError(error);
      console.error("Error sending message:", error);
      return false;
    }
  }, []);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      messageHandlers.current.clear();
    };
  }, []);

  return {
    sendMessage,
    lastMessage,
    error,
    isConnected,
    unsubscribe: () => {
      messageHandlers.current.clear();
    }
  };
}