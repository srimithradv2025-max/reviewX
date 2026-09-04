import React, { useState, useEffect, useCallback, useRef } from "react";
import { DiagnosticCard } from "./components/DiagnosticCard";
import { VerificationModal } from "./components/VerificationModal";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { useWebviewProtocol } from "./hooks/useWebviewProtocol";
import { scanCode, type ScanRequestPayload } from "./services/apiService";
import { buildVerificationQuiz, type VerificationQuiz } from "./utils/verificationQuiz";
import { buildFixEdits } from "./utils/fixEdits";
import {
  ReviewXCommand,
  isJsonRpcResponse,
  isJsonRpcErrorResponse,
  type DiagnosticItem,
  type JsonRpcId,
  type JsonRpcSuccessResponse,
  type ScanFileParams,
  type ScanFileResult,
  type ApplyCodeFixParams
} from "../types/protocol";

// ─── SVG Icon Components ─────────────────────────────────────────────────────

const BridgeIcon = () => (
  <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M2 12h4l3-9 6 18 3-9h4" />
    <circle cx="12" cy="12" r="2" fill="currentColor" />
  </svg>
);

const ScanIcon = () => (
  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M3 7V5a2 2 0 0 1 2-2h2" />
    <path d="M17 3h2a2 2 0 0 1 2 2v2" />
    <path d="M21 17v2a2 2 0 0 1-2 2h-2" />
    <path d="M7 21H5a2 2 0 0 1-2-2v-2" />
    <rect x="7" y="7" width="10" height="10" rx="1" />
  </svg>
);

const EmptyIcon = () => (
  <svg width="52" height="52" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1" strokeLinecap="round" strokeLinejoin="round" className="opacity-40">
    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
    <polyline points="14 2 14 8 20 8" />
    <line x1="9" y1="13" x2="15" y2="13" />
    <line x1="9" y1="17" x2="15" y2="17" />
  </svg>
);

function App() {
  const { sendMessage, lastMessage } = useWebviewProtocol();
  const [isScanning, setIsScanning] = useState(false);
  const [diagnostics, setDiagnostics] = useState<DiagnosticItem[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [activeQuiz, setActiveQuiz] = useState<VerificationQuiz | null>(null);
  const [pendingFix, setPendingFix] = useState<DiagnosticItem | null>(null);
  const pendingScanId = useRef<JsonRpcId | null>(null);
  const scanGeneration = useRef(0);
  const renderedUri = useRef<string | null>(null);
  const scanLanguageId = useRef<string | undefined>(undefined);

  // Handle view resolution and initial state
  useEffect(() => {
    // Notify extension host that webview is ready
    sendMessage({
      jsonrpc: "2.0",
      method: "ON_WEBVIEW_READY",
      params: { timestamp: Date.now() }
    });
  }, [sendMessage]);

  const runBackendScan = useCallback(
    async (payload: ScanRequestPayload) => {
      const generation = ++scanGeneration.current;
      const isCurrent = () => generation === scanGeneration.current;
      setIsScanning(true);
      setError(null);
      try {
        const result = await scanCode(payload);
        if (!isCurrent()) return;
        setDiagnostics(result.diagnostics ?? []);
        scanLanguageId.current = result.languageId ?? payload.languageId;
        renderedUri.current = result.uri;
        await sendMessage({
          jsonrpc: "2.0",
          id: Date.now(),
          method: ReviewXCommand.RENDER_DIAGNOSTIC,
          params: {
            uri: result.uri,
            diagnostics: result.diagnostics ?? [],
            clearPrevious: true
          }
        });
      } catch (err) {
        if (!isCurrent()) return;
        setDiagnostics([]);
        const message = err instanceof Error ? err.message : "Scan failed.";
        const staleUri = renderedUri.current ?? payload.uri;
        let clearFailure = "";
        if (staleUri) {
          try {
            await sendMessage({
              jsonrpc: "2.0",
              id: Date.now(),
              method: ReviewXCommand.RENDER_DIAGNOSTIC,
              params: { uri: staleUri, diagnostics: [], clearPrevious: true }
            });
            renderedUri.current = null;
          } catch {
            clearFailure = " Previous editor findings could not be cleared.";
          }
        }
        if (isCurrent()) setError(`${message}${clearFailure}`);
      } finally {
        if (isCurrent()) setIsScanning(false);
      }
    },
    [sendMessage]
  );

  // Handle incoming messages from extension host
  useEffect(() => {
    if (!lastMessage) return;

    // Host-initiated scan (e.g. the "Scan Active File" command).
    if ("method" in lastMessage && lastMessage.method === ReviewXCommand.SCAN_FILE) {
      const params = (lastMessage as { params?: ScanFileParams }).params;
      if (params?.content !== undefined) {
        void runBackendScan({
          uri: params.uri,
          content: params.content,
          languageId: params.languageId
        });
      }
      return;
    }

    if (!isJsonRpcResponse(lastMessage) || lastMessage.id !== pendingScanId.current) return;
    pendingScanId.current = null;

    if (isJsonRpcErrorResponse(lastMessage)) {
      setIsScanning(false);
      setError(lastMessage.error.message);
      return;
    }

    const result = (lastMessage as JsonRpcSuccessResponse<ScanFileResult>).result;
    void runBackendScan({
      uri: result.uri,
      content: result.content,
      languageId: result.languageId
    });
  }, [lastMessage, runBackendScan]);

  const handleScanFile = async () => {
    setIsScanning(true);
    setError(null);
    const id = Date.now();
    pendingScanId.current = id;
    await sendMessage({
      jsonrpc: "2.0",
      id,
      method: ReviewXCommand.SCAN_FILE,
      params: {} as ScanFileParams
    });
  };

  const handleRequestFix = (diagnostic: DiagnosticItem) => {
    setPendingFix(diagnostic);
    setActiveQuiz(buildVerificationQuiz(diagnostic));
  };

  const closeVerification = useCallback(() => {
    setPendingFix(null);
    setActiveQuiz(null);
  }, []);

  const handleVerificationComplete = async (verified: boolean) => {
    const diagnostic = pendingFix;
    if (verified && diagnostic) {
      const edits = buildFixEdits(diagnostic, scanLanguageId.current);
      if (!edits) {
        setError(`No applicable fix is available for '${diagnostic.id}'.`);
        closeVerification();
        return;
      }
      const params: ApplyCodeFixParams = {
        uri: diagnostic.uri ?? renderedUri.current ?? "",
        fixId: diagnostic.id,
        title: diagnostic.fix?.title ?? diagnostic.message,
        diagnosticId: diagnostic.id,
        edits,
        preserveCursor: true
      };
      await sendMessage({
        jsonrpc: "2.0",
        id: Date.now(),
        method: ReviewXCommand.APPLY_CODE_FIX,
        params
      });
    }
    closeVerification();
  };

  const hasCritical = diagnostics.some(d => d.severity === "error");
  const criticalCount = diagnostics.filter(d => d.severity === "error").length;
  const warningCount = diagnostics.filter(d => d.severity === "warning").length;

  return (
    <ErrorBoundary fallback={<div className="p-4 text-vscode-editor-foreground">An error occurred</div>}>
      <div className="h-full w-full flex flex-col bg-vscode-editor-background text-vscode-editor-foreground">

        {/* ─── Sleek Header ─────────────────────────────────────────────── */}
        <header className="relative flex items-center justify-between px-5 py-3.5 border-b border-subtle bg-subtle-gradient">
          {/* Left: Brand + version */}
          <div className="flex items-center gap-3">
            <div className="flex items-center justify-center w-9 h-9 rounded-lg bg-vscode-activityBar-background/60 border border-vscode-input-border">
              <BridgeIcon />
            </div>
            <div className="flex flex-col">
              <h1 className="text-base font-semibold leading-tight tracking-tight">
                ReviewX
              </h1>
              <span className="text-[10px] text-vscode-editor-foreground/50 font-medium">
                v0.1.0
              </span>
            </div>
          </div>

          {/* Right: Stats pill + scan button */}
          <div className="flex items-center gap-3">
            {diagnostics.length > 0 && (
              <div className="flex items-center gap-2 px-2.5 py-1 rounded-full bg-vscode-input-background/50 border border-vscode-input-border">
                {hasCritical && (
                  <span className="flex items-center gap-1 text-[10px] font-medium text-vscode-problemsErrorIcon-foreground">
                    <span className="w-1.5 h-1.5 rounded-full bg-vscode-problemsErrorIcon-foreground animate-pulse" />
                    {criticalCount}
                  </span>
                )}
                {warningCount > 0 && (
                  <span className="flex items-center gap-1 text-[10px] font-medium text-vscode-problemsWarningIcon-foreground">
                    <span className="w-1.5 h-1.5 rounded-full bg-vscode-problemsWarningIcon-foreground" />
                    {warningCount}
                  </span>
                )}
              </div>
            )}
            <button
              onClick={handleScanFile}
              disabled={isScanning}
              className="group flex items-center gap-2 px-4 py-2 text-sm font-medium bg-vscode-button-background text-vscode-button-foreground rounded-lg hover:bg-vscode-button-hoverBackground disabled:opacity-50 disabled:cursor-not-allowed transition-all duration-150 hover:shadow-md hover:shadow-black/20 active:scale-[0.98]"
            >
              <ScanIcon />
              <span>{isScanning ? "Scanning..." : "Scan File"}</span>
            </button>
          </div>
        </header>

        {/* ─── Main Content Area ─────────────────────────────────────────── */}
        <main className="flex-1 overflow-auto p-5 scrollbar-thin">
          {error && (
            <div className="mb-4 rounded-lg border border-vscode-input-border bg-vscode-input-background/40 px-3 py-2 text-xs text-vscode-problemsErrorIcon-foreground">
              {error}
            </div>
          )}
          {diagnostics.length > 0 ? (
            <div className="space-y-4 max-w-2xl">
              {/* Section label */}
              <div className="flex items-center gap-2 mb-2">
                <span className="text-[10px] font-semibold uppercase tracking-widest text-vscode-editor-foreground/40">
                  Findings
                </span>
                <div className="flex-1 h-px bg-vscode-input-border/50" />
                <span className="text-[10px] text-vscode-editor-foreground/40">
                  {diagnostics.length} issue{diagnostics.length !== 1 ? "s" : ""} detected
                </span>
              </div>
              {diagnostics.map((diagnostic, index) => (
                <div
                  key={diagnostic.id}
                  className="animate-[slide-up-fade_0.3s_ease-out_forwards]"
                  style={{ animationDelay: `${index * 60}ms`, opacity: 0 }}
                >
                  <DiagnosticCard
                    diagnostic={diagnostic}
                    onApplyFix={handleRequestFix}
                  />
                </div>
              ))}
            </div>
          ) : (
            /* ─── Empty State ─────────────────────────────────────────── */
            <div className="flex flex-col items-center justify-center h-full min-h-[300px] text-center">
              <div className="relative mb-6">
                <div className="absolute inset-0 bg-vscode-activityBarBadge-background/10 rounded-full blur-xl" />
                <div className="relative flex items-center justify-center w-20 h-20 rounded-2xl bg-vscode-input-background/40 border border-vscode-input-border">
                  <EmptyIcon />
                </div>
              </div>
              <p className="text-sm font-medium text-vscode-editor-foreground/70 mb-1.5">
                No diagnostics found
              </p>
              <p className="text-xs text-vscode-editor-foreground/40 max-w-[220px]">
                Open a file and click{" "}
                <span className="text-vscode-editor-foreground/60 font-medium">Scan File</span>{" "}
                to begin analysis
              </p>
            </div>
          )}
        </main>

        {/* ─── Verification Modal ─────────────────────────────────────────── */}
        {pendingFix && (
          <VerificationModal
            quiz={activeQuiz}
            onVerified={handleVerificationComplete}
            onCancel={closeVerification}
          />
        )}
      </div>
    </ErrorBoundary>
  );
}

export default App;