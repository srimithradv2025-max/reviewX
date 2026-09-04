import React, { useEffect, useState } from "react";
import { verifyAnswer } from "../services/apiService";
import type { VerificationQuiz } from "../utils/verificationQuiz";

export interface VerificationModalProps {
  quiz: VerificationQuiz | null;
  onVerified: (verified: boolean) => void;
  onCancel: () => void;
}

export const VerificationModal: React.FC<VerificationModalProps> = ({
  quiz,
  onVerified,
  onCancel
}) => {
  const [selectedOptionId, setSelectedOptionId] = useState<string | null>(null);
  const [isChecking, setIsChecking] = useState(false);
  const [feedback, setFeedback] = useState<string | null>(null);
  const [isCorrect, setIsCorrect] = useState<boolean | null>(null);

  const hasOptions = Boolean(quiz && quiz.options.length > 0);

  // Nothing to ask: dismiss instead of rendering an empty overlay.
  useEffect(() => {
    if (!hasOptions) onCancel();
  }, [hasOptions, onCancel]);

  if (!quiz || !hasOptions) return null;

  const handleSubmit = async () => {
    if (!selectedOptionId) return;
    setIsChecking(true);
    setFeedback(null);
    const locallyCorrect = selectedOptionId === quiz.correctOptionId;
    try {
      const result = await verifyAnswer({
        questionId: quiz.questionId,
        selectedOptionId,
        codeSnippet: quiz.codeSnippet
      });
      // The backend leaves isCorrect null when no LLM provider is configured;
      // fall back to the locally known correct option in that case.
      const verified = result.isCorrect ?? locallyCorrect;
      setIsCorrect(verified);
      setFeedback(result.feedback);
    } catch {
      setIsCorrect(locallyCorrect);
      setFeedback(
        locallyCorrect
          ? "Backend unreachable — answer checked locally: correct."
          : "Backend unreachable — answer checked locally: incorrect."
      );
    } finally {
      setIsChecking(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
      role="dialog"
      aria-modal="true"
      aria-label="Verify answer"
      onClick={onCancel}
    >
      <div
        className="w-full max-w-md rounded-xl border border-vscode-input-border bg-vscode-editor-background p-5 shadow-xl"
        onClick={event => event.stopPropagation()}
      >
        <header className="mb-3">
          <h2 className="text-sm font-semibold text-vscode-editor-foreground">
            Comprehension Verification
          </h2>
          <p className="mt-1 text-xs text-vscode-editor-foreground/60">{quiz.question}</p>
        </header>

        <div className="space-y-2">
          {quiz.options.map(option => {
            const selected = selectedOptionId === option.id;
            return (
              <button
                key={option.id}
                type="button"
                onClick={() => {
                  setSelectedOptionId(option.id);
                  setFeedback(null);
                  setIsCorrect(null);
                }}
                className={`block w-full rounded-lg border px-3 py-2 text-left text-xs transition-colors ${
                  selected
                    ? "border-vscode-activityBarBadge-background bg-vscode-input-background text-vscode-editor-foreground"
                    : "border-vscode-input-border bg-vscode-input-background/40 text-vscode-editor-foreground/80 hover:bg-vscode-input-background"
                }`}
              >
                {option.label}
              </button>
            );
          })}
        </div>

        {feedback && (
          <p
            className={`mt-3 text-xs ${
              isCorrect
                ? "text-vscode-problemsInfoIcon-foreground"
                : "text-vscode-problemsErrorIcon-foreground"
            }`}
          >
            {feedback}
          </p>
        )}

        <footer className="mt-5 flex items-center justify-end gap-2">
          <button
            type="button"
            onClick={onCancel}
            className="rounded-lg border border-vscode-input-border px-3 py-2 text-xs text-vscode-editor-foreground/80 hover:bg-vscode-input-background"
          >
            Cancel
          </button>
          {isCorrect ? (
            <button
              type="button"
              onClick={() => onVerified(true)}
              className="rounded-lg bg-vscode-button-background px-3 py-2 text-xs font-medium text-vscode-button-foreground hover:bg-vscode-button-hoverBackground"
            >
              Apply Verified Fix
            </button>
          ) : (
            <button
              type="button"
              disabled={!selectedOptionId || isChecking}
              onClick={handleSubmit}
              className="rounded-lg bg-vscode-button-background px-3 py-2 text-xs font-medium text-vscode-button-foreground hover:bg-vscode-button-hoverBackground disabled:cursor-not-allowed disabled:opacity-50"
            >
              {isChecking ? "Verifying..." : "Verify Answer"}
            </button>
          )}
        </footer>
      </div>
    </div>
  );
};
