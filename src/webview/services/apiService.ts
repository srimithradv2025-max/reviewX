/**
 * ReviewX REST API service.
 *
 * All webview requests are routed to the local FastAPI backend at
 * http://127.0.0.1:8000/api/v1/.
 */

import type { DiagnosticItem } from "../../types/protocol";

export const API_BASE_URL = "http://127.0.0.1:8000/api/v1";

const REQUEST_TIMEOUT_MS = 15000;

export interface ScanRequestPayload {
  uri?: string;
  content?: string;
  languageId?: string;
  options?: {
    includeAst?: boolean;
    maxDiagnostics?: number;
    includeWorkspaceContext?: boolean;
  };
}

export interface ScanApiResult {
  uri: string;
  languageId: string;
  lineCount: number;
  symbolsScanned: number;
  findingsCount: number;
  timestamp: string;
  diagnostics: DiagnosticItem[];
}

export interface ExplainRequestPayload {
  uri?: string;
  diagnosticId?: string;
  ruleId?: string;
  languageId?: string;
  snippet?: string;
}

export interface ExplainApiResult {
  explanation: string;
  steps: string[];
  timestamp: string;
}

export interface VerifyRequestPayload {
  questionId: string;
  challengeId?: string;
  selectedOptionId?: string;
  textAnswer?: string;
  codeSnippet?: string;
  metadata?: Record<string, unknown>;
}

export interface VerifyApiResult {
  questionId: string;
  isCorrect: boolean | null;
  score: number | null;
  feedback: string;
  explanation?: string | null;
  hints: string[];
  nextChallengeId?: string | null;
  timestamp: number;
}

export class ApiError extends Error {
  constructor(message: string, public readonly status?: number) {
    super(message);
    this.name = "ApiError";
  }
}

async function postJson<TResult>(path: string, body: unknown): Promise<TResult> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);

  try {
    const response = await fetch(`${API_BASE_URL}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal: controller.signal
    });

    if (!response.ok) {
      const detail = await response.text().catch(() => "");
      throw new ApiError(
        `ReviewX backend returned ${response.status} for ${path}${detail ? `: ${detail}` : ""}`,
        response.status
      );
    }

    return (await response.json()) as TResult;
  } catch (err) {
    if (err instanceof ApiError) throw err;
    if (err instanceof DOMException && err.name === "AbortError") {
      throw new ApiError(`Request to ${path} timed out after ${REQUEST_TIMEOUT_MS}ms.`);
    }
    throw new ApiError(
      `Cannot reach the ReviewX backend at ${API_BASE_URL}. Start it with 'uvicorn app.main:app --port 8000'.`
    );
  } finally {
    clearTimeout(timeout);
  }
}

export function scanCode(payload: ScanRequestPayload): Promise<ScanApiResult> {
  return postJson<ScanApiResult>("/scan", payload);
}

export function explainFinding(payload: ExplainRequestPayload): Promise<ExplainApiResult> {
  return postJson<ExplainApiResult>("/explain", payload);
}

export function verifyAnswer(payload: VerifyRequestPayload): Promise<VerifyApiResult> {
  return postJson<VerifyApiResult>("/verify", payload);
}
