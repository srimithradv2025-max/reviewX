/**
 * Protocol definitions for the ReviewX VS Code Extension.
 * Defines JSON-RPC 2.0 message contracts for bi-directional communication
 * between the Extension Host and the Webview Sidebar Provider.
 */

// ============================================================================
// JSON-RPC 2.0 Base Protocol Specifications
// ============================================================================

export type JsonRpcVersion = "2.0";
export type JsonRpcId = string | number;

export enum JsonRpcErrorCode {
  ParseError = -32700,
  InvalidRequest = -32600,
  MethodNotFound = -32601,
  InvalidParams = -32602,
  InternalError = -32603,
  FileAccessError = -32001,
  DiagnosticError = -32002,
  VerificationError = -32003,
  ApplyFixError = -32004,
  EditorNotFound = -32005
}

export interface JsonRpcError<TData = unknown> {
  code: number;
  message: string;
  data?: TData;
}

export interface JsonRpcRequest<TMethod extends string = string, TParams = unknown> {
  jsonrpc: JsonRpcVersion;
  id: JsonRpcId;
  method: TMethod;
  params: TParams;
}

export interface JsonRpcNotification<TMethod extends string = string, TParams = unknown> {
  jsonrpc: JsonRpcVersion;
  method: TMethod;
  params?: TParams;
}

export interface JsonRpcSuccessResponse<TResult = unknown> {
  jsonrpc: JsonRpcVersion;
  id: JsonRpcId;
  result: TResult;
  error?: never;
}

export interface JsonRpcErrorResponse<TData = unknown> {
  jsonrpc: JsonRpcVersion;
  id: JsonRpcId | null;
  error: JsonRpcError<TData>;
  result?: never;
}

export type JsonRpcResponse<TResult = unknown, TData = unknown> =
  | JsonRpcSuccessResponse<TResult>
  | JsonRpcErrorResponse<TData>;

export type JsonRpcMessage =
  | JsonRpcRequest
  | JsonRpcNotification
  | JsonRpcResponse;

// ============================================================================
// Shared Domain Data Models
// ============================================================================

export interface Position {
  line: number;      // 0-indexed line number
  character: number; // 0-indexed character position
}

export interface Range {
  start: Position;
  end: Position;
}

export type DiagnosticSeverity = "error" | "warning" | "information" | "hint";

export interface DiagnosticRelatedInformation {
  range: Range;
  message: string;
  uri: string;
}

/**
 * A concrete, machine-applicable fix: `newText` is valid source code that
 * replaces exactly `range`. Prose guidance belongs in `recommendation`.
 */
export interface CodeFix {
  range: Range;
  newText: string;
  title?: string;
}

export interface DiagnosticItem {
  id: string;
  message: string;
  range: Range;
  severity: DiagnosticSeverity;
  source?: string;
  code?: string | number;
  relatedInformation?: DiagnosticRelatedInformation[];
  category?: string;
  snippet?: string;
  recommendation?: string;
  fix?: CodeFix;
  title?: string;
  uri?: string;
}


// ============================================================================
// Command Type Constants
// ============================================================================

export const ReviewXCommand = {
  SCAN_FILE: "SCAN_FILE",
  RENDER_DIAGNOSTIC: "RENDER_DIAGNOSTIC",
  VERIFY_ANSWER: "VERIFY_ANSWER",
  APPLY_CODE_FIX: "APPLY_CODE_FIX"
} as const;

export type ReviewXCommandType =
  (typeof ReviewXCommand)[keyof typeof ReviewXCommand];

// ============================================================================
// Command Payload Definitions: SCAN_FILE
// ============================================================================

export interface ScanFileOptions {
  includeAst?: boolean;
  maxDiagnostics?: number;
  includeWorkspaceContext?: boolean;
}

export interface ScanFileParams {
  uri?: string;
  content?: string;
  languageId?: string;
  options?: ScanFileOptions;
}

export interface ScanFileResult {
  uri: string;
  languageId: string;
  content: string;
  lineCount: number;
  symbolsScanned: number;
  findingsCount: number;
  timestamp: number;
  diagnostics: DiagnosticItem[];
}

export type ScanFileRequest = JsonRpcRequest<
  typeof ReviewXCommand.SCAN_FILE,
  ScanFileParams
>;
export type ScanFileResponse = JsonRpcSuccessResponse<ScanFileResult>;

// ============================================================================
// Command Payload Definitions: RENDER_DIAGNOSTIC
// ============================================================================

export interface RenderDiagnosticParams {
  uri: string;
  diagnostics: DiagnosticItem[];
  clearPrevious?: boolean;
  owner?: string;
}

export interface RenderDiagnosticResult {
  uri: string;
  renderedCount: number;
  success: boolean;
  timestamp: number;
}

export type RenderDiagnosticRequest = JsonRpcRequest<
  typeof ReviewXCommand.RENDER_DIAGNOSTIC,
  RenderDiagnosticParams
>;
export type RenderDiagnosticResponse = JsonRpcSuccessResponse<RenderDiagnosticResult>;

// ============================================================================
// Command Payload Definitions: VERIFY_ANSWER
// ============================================================================

export interface VerifyAnswerParams {
  questionId: string;
  challengeId?: string;
  selectedOptionId?: string;
  textAnswer?: string;
  codeSnippet?: string;
  metadata?: Record<string, unknown>;
}

export interface VerifyAnswerResult {
  questionId: string;
  isCorrect: boolean;
  score?: number;
  feedback: string;
  explanation?: string;
  hints?: string[];
  nextChallengeId?: string;
  timestamp: number;
}

export type VerifyAnswerRequest = JsonRpcRequest<
  typeof ReviewXCommand.VERIFY_ANSWER,
  VerifyAnswerParams
>;
export type VerifyAnswerResponse = JsonRpcSuccessResponse<VerifyAnswerResult>;

// ============================================================================
// Command Payload Definitions: APPLY_CODE_FIX
// ============================================================================

export interface ApplyCodeFixParams {
  uri: string;
  fixId: string;
  title: string;
  diagnosticId?: string;
  edits: TextEditItem[];
  preserveCursor?: boolean;
}

export interface ApplyCodeFixResult {
  uri: string;
  fixId: string;
  appliedEditsCount: number;
  success: boolean;
  message?: string;
  timestamp: number;
}

// ============================================================================
// Type Mappings & Aggregations
// ============================================================================

export interface BridgeCommandParamsMap {
  [ReviewXCommand.SCAN_FILE]: ScanFileParams;
  [ReviewXCommand.RENDER_DIAGNOSTIC]: RenderDiagnosticParams;
  [ReviewXCommand.VERIFY_ANSWER]: VerifyAnswerParams;
  [ReviewXCommand.APPLY_CODE_FIX]: ApplyCodeFixParams;
}

export interface BridgeCommandResultMap {
  [ReviewXCommand.SCAN_FILE]: ScanFileResult;
  [ReviewXCommand.RENDER_DIAGNOSTIC]: RenderDiagnosticResult;
  [ReviewXCommand.VERIFY_ANSWER]: VerifyAnswerResult;
  [ReviewXCommand.APPLY_CODE_FIX]: ApplyCodeFixResult;
}

export type BridgeRequest =
  | ScanFileRequest
  | RenderDiagnosticRequest
  | VerifyAnswerRequest
  | ApplyCodeFixRequest;

export type BridgeSuccessResponse =
  | ScanFileResponse
  | RenderDiagnosticResponse
  | VerifyAnswerResponse
  | ApplyCodeFixResponse;

export type BridgeResponse = BridgeSuccessResponse | JsonRpcErrorResponse;

// ============================================================================
// JSON-RPC Protocol Helpers and Type Guards
// ============================================================================

export function createJsonRpcRequest<K extends ReviewXCommandType>(
  id: JsonRpcId,
  method: K,
  params: BridgeCommandParamsMap[K]
): JsonRpcRequest<K, BridgeCommandParamsMap[K]> {
  return {
    jsonrpc: "2.0",
    id,
    method,
    params
  };
}

export function createJsonRpcSuccessResponse<TResult>(
  id: JsonRpcId,
  result: TResult
): JsonRpcSuccessResponse<TResult> {
  return {
    jsonrpc: "2.0",
    id,
    result
  };
}

export function createJsonRpcErrorResponse(
  id: JsonRpcId | null,
  code: number,
  message: string,
  data?: unknown
): JsonRpcErrorResponse {
  return {
    jsonrpc: "2.0",
    id,
    error: {
      code,
      message,
      data
    }
  };
}

export function createJsonRpcNotification<TMethod extends string, TParams>(
  method: TMethod,
  params?: TParams
): JsonRpcNotification<TMethod, TParams> {
  return {
    jsonrpc: "2.0",
    method,
    params
  };
}

export function isJsonRpcRequest(message: unknown): message is JsonRpcRequest {
  return (
    typeof message === "object" &&
    message !== null &&
    (message as JsonRpcRequest).jsonrpc === "2.0" &&
    "id" in message &&
    typeof (message as JsonRpcRequest).method === "string" &&
    "params" in message
  );
}

export function isJsonRpcResponse(message: unknown): message is JsonRpcResponse {
  return (
    typeof message === "object" &&
    message !== null &&
    (message as JsonRpcResponse).jsonrpc === "2.0" &&
    "id" in message &&
    ("result" in message || "error" in message)
  );
}

export function isJsonRpcErrorResponse(
  message: unknown
): message is JsonRpcErrorResponse {
  return (
    isJsonRpcResponse(message) &&
    "error" in message &&
    typeof (message as JsonRpcErrorResponse).error === "object" &&
    (message as JsonRpcErrorResponse).error !== null
  );
}

export function isJsonRpcNotification(
  message: unknown
): message is JsonRpcNotification {
  return (
    typeof message === "object" &&
    message !== null &&
    (message as JsonRpcNotification).jsonrpc === "2.0" &&
    !("id" in message) &&
    typeof (message as JsonRpcNotification).method === "string"
  );
}

export type ApplyCodeFixRequest = JsonRpcRequest<
  typeof ReviewXCommand.APPLY_CODE_FIX,
  ApplyCodeFixParams
>;
export type ApplyCodeFixResponse = JsonRpcSuccessResponse<ApplyCodeFixResult>;

export interface TextEditItem {
  range: Range;
  newText: string;
}
