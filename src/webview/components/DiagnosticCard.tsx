import React, { useState, useCallback } from "react";
import type { DiagnosticItem, DiagnosticSeverity } from "../../types/protocol";
import { useWebviewProtocol } from "../hooks/useWebviewProtocol";

export interface DiagnosticCardProps {
  diagnostic: DiagnosticItem;
  onApplyFix?: (diagnosticId?: string) => void;
}

const severityLabels: Record<DiagnosticSeverity, string> = {
  error: "critical issue",
  warning: "potential concern",
  information: "informational note",
  hint: "helpful tip"
};

const severityDescriptions: Record<DiagnosticSeverity, string> = {
  error: "This code pattern needs immediate attention.",
  warning: "This pattern could cause problems later.",
  information: "General informational message.",
  hint: "Consider this improvement for better code quality."
};

const severityClass: Record<DiagnosticSeverity, string> = {
  error: "critical",
  warning: "warning",
  information: "info",
  hint: "hint"
};

const SourceIcon = () => (
  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
    <path d="M12 2L4 6v6c0 5 3.5 9 8 10 4.5-1 8-5 8-10V6l-8-4z" />
  </svg>
);

const LocationIcon = () => (
  <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <line x1="8" y1="6" x2="21" y2="6" />
    <line x1="8" y1="12" x2="21" y2="12" />
    <line x1="8" y1="18" x2="21" y2="18" />
    <line x1="3" y1="6" x2="3.01" y2="6" />
    <line x1="3" y1="12" x2="3.01" y2="12" />
    <line x1="3" y1="18" x2="3.01" y2="18" />
  </svg>
);

const CopyIcon = () => (
  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
    <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
  </svg>
);

const CheckIcon = () => (
  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
    <polyline points="20 6 9 17 4 12" />
  </svg>
);

const DetailsIcon = () => (
  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="12" cy="12" r="10" />
    <line x1="12" y1="16" x2="12" y2="12" />
    <line x1="12" y1="8" x2="12.01" y2="8" />
  </svg>
);

const WandIcon = () => (
  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M15 4V2" />
    <path d="M15 16v-2" />
    <path d="M8 9h2" />
    <path d="M20 9h2" />
    <path d="M17.8 11.8L19 13" />
    <path d="M17.8 6.2L19 5" />
    <path d="M3 21l9-9" />
    <path d="M12.2 6.2L11 5" />
  </svg>
);


export const DiagnosticCard: React.FC<DiagnosticCardProps> = ({
  diagnostic,
  onApplyFix
}) => {
  const { sendMessage } = useWebviewProtocol();
  const [copied, setCopied] = useState(false);

  const severity = diagnostic.severity ?? "information";
  const description = severityDescriptions[severity] ?? "General informational message.";
  const plainLanguageLabel = severityLabels[severity] ?? "issue";
  const sourceLabel = diagnostic.category ?? "Code Quality";
  const recommendation = diagnostic.recommendation ?? "";

  const oldContent = diagnostic.title ?? "Original code";
  const newContent = recommendation ?? "Fixed code";

  const handleApplyFix = async () => {
    const params = {
      uri: diagnostic.uri ?? "",
      fixId: diagnostic.id,
      title: diagnostic.message,
      edits: diagnostic.relatedInformation?.map(related => ({
        range: related.range,
        newText: recommendation ?? ""
      })) ?? [],
      preserveCursor: true
    };

    await sendMessage({
      jsonrpc: "2.0",
      id: Date.now(),
      method: "APPLY_CODE_FIX",
      params
    });

    onApplyFix?.(diagnostic.id);
  };

  const handleCopy = useCallback(async () => {
    const text = `- ${oldContent}\n+ ${newContent}`;
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // Silently no-op if clipboard API unavailable
    }
  }, [oldContent, newContent]);


  return (
    <div className="group relative rounded-lg border border-subtle bg-vscode-input-background/40 p-4 shadow-sm hover:border-vscode-activityBarBadge-background/50 transition-all duration-200">
      <div className="absolute inset-0 rounded-lg bg-subtle-gradient opacity-0 group-hover:opacity-30 transition-opacity duration-300 pointer-events-none" />
      <div className="relative">
        <header className="flex items-center justify-between gap-2 mb-3">
          <div className="source-badge">
            <SourceIcon />
            <span>{sourceLabel}</span>
          </div>
          <div className={`severity-badge ${severityClass[severity]}`}>
            <span className="w-1.5 h-1.5 rounded-full bg-current" />
            <span className="capitalize">{severity}</span>
          </div>
        </header>
        <h3 className="text-sm font-medium text-vscode-editor-foreground leading-snug mb-1.5">
          {description}
        </h3>
        <div className="flex items-center gap-3 text-[11px] text-vscode-editor-foreground/50 mb-4">
          <span className="inline-flex items-center gap-1">
            <LocationIcon />
            Line {diagnostic.range?.start.line + 1}
          </span>
          <span className="w-0.5 h-0.5 rounded-full bg-vscode-editor-foreground/30" />
          <span className="capitalize">{plainLanguageLabel}</span>
        </div>
        <div className="code-diff-container">
          <button
            onClick={handleCopy}
            className="absolute top-2 right-2 flex items-center gap-1 px-2 py-1 text-[10px] font-medium text-vscode-editor-foreground/60 hover:text-vscode-editor-foreground bg-vscode-input-background/80 hover:bg-vscode-input-background border border-vscode-input-border rounded opacity-0 group-hover:opacity-100 transition-all duration-200 hover:scale-105"
            title="Copy diff to clipboard"
          >
            {copied ? <><CheckIcon /><span>Copied</span></> : <><CopyIcon /><span>Copy</span></>}
          </button>
          <div className="grid grid-cols-2 divide-x divide-vscode-input-border/50">
            <div className="p-3">
              <div className="text-[10px] font-semibold uppercase tracking-wider text-vscode-editor-foreground/40 mb-2">Original</div>
              <pre className="text-[11px] leading-relaxed whitespace-pre-wrap font-mono text-vscode-editor-foreground/80 max-h-40 overflow-auto scrollbar-thin">
                {oldContent.split("\n").map((line: string, i: number) => (
                  <div key={`old-${i}`} className="flex group/line hover:bg-vscode-diffEditor-removedTextBackground/40 transition-colors">
                    <span className="w-6 text-right mr-3 text-vscode-editor-foreground/30 select-none flex-shrink-0">{i + 1}</span>
                    <span className="text-vscode-problemsErrorIcon-foreground select-none w-3 flex-shrink-0">-</span>
                    <span className="ml-1.5 break-all">{line || "\u00A0"}</span>
                  </div>
                ))}
              </pre>
            </div>
            <div className="p-3">
              <div className="text-[10px] font-semibold uppercase tracking-wider text-vscode-editor-foreground/40 mb-2">Updated</div>
              <pre className="text-[11px] leading-relaxed whitespace-pre-wrap font-mono text-vscode-editor-foreground/80 max-h-40 overflow-auto scrollbar-thin">
                {newContent.split("\n").map((line: string, i: number) => (
                  <div key={`new-${i}`} className="flex group/line hover:bg-vscode-diffEditor-insertedTextBackground/40 transition-colors">
                    <span className="w-6 text-right mr-3 text-vscode-editor-foreground/30 select-none flex-shrink-0">{i + 1}</span>
                    <span className="text-vscode-problemsInfoIcon-foreground select-none w-3 flex-shrink-0">+</span>
                    <span className="ml-1.5 break-all">{line || "\u00A0"}</span>
                  </div>
                ))}
              </pre>
            </div>
          </div>
        </div>
        <div className="flex gap-2 pt-4 mt-1">
          <button
            onClick={handleApplyFix}
            className="group/btn flex-1 flex items-center justify-center gap-2 px-3 py-2 text-sm font-medium bg-vscode-button-background text-vscode-button-foreground rounded-lg hover:bg-vscode-button-hoverBackground transition-all duration-150 active:scale-[0.98] hover:shadow-md hover:shadow-black/20"
          >
            <WandIcon />
            <span>Apply Fix to Editor</span>
          </button>
          <button
            onClick={() => sendMessage({
              jsonrpc: "2.0",
              id: Date.now(),
              method: "reviewX.requestDetails",
              params: { diagnosticId: diagnostic.id }
            })}
            className="flex items-center gap-1.5 px-3 py-2 text-xs font-medium bg-vscode-input-background/50 text-vscode-input-foreground rounded-lg border border-vscode-input-border hover:bg-vscode-input-background hover:border-vscode-activityBarBadge-background/50 transition-all duration-150"
          >
            <DetailsIcon />
            <span>Details</span>
          </button>
        </div>
      </div>
    </div>
  );
};
