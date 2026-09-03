import React, { useState } from "react";
import type {
  VerifyAnswerParams,
  VerifyAnswerResult
} from "../../types/protocol";

/**
 * VerificationModal - 3-option multiple-choice comprehension gate
 * Tests the developer's understanding of the root cause
 * Keeps the "Apply Fix to Editor" button disabled until correct answer is chosen
 * Dispatches an APPLY_CODE_FIX message back to the Extension Host when approved
 */

export interface VerificationModalProps {
  onVerified?: (verified: boolean) => void;
  onCancel?: () => void;
}

const OPTIONS = [
  {
    id: "option1",
    text: "The code violates security policy – remove the hardcoded secret",
    correct: false
  },
  {
    id: "option2",
    text: "The logic is unclear – add comments explaining the intent",
    correct: true
  },
  {
    id: "option3",
    text: "Performance optimization is needed – cache expensive computations",
    correct: false
  }
];

export const VerificationModal: React.FC<VerificationModalProps> = ({
  onVerified,
  onCancel
}) => {
  const [selected, setSelected] = useState<string | null>(null);

  const handleSelect = (optionId: string) => {
    setSelected(optionId);
  };

  const handleVerify = () => {
    const selectedOption = OPTIONS.find(opt => opt.id === selected);
    if (selectedOption?.correct) {
      onVerified?.(true);
    } else {
      onCancel?.();
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-vscode-editor-background/50 backdrop-blur-sm">
      <div className="bg-vscode-editor-background rounded-lg border border-vscode-input-border p-6 max-w-md w-full max-h-[90vh]">
        <h3 className="text-lg font-semibold text-vscode-editor-foreground mb-4">
          Verify Answer
        </h3>

        {selected === null ? (
          <div className="text-center text-xs text-vscode-editor-foreground/60 mb-4">
            Select the correct answer to proceed
          </div>
        ) : (
          <>
            <div className="mb-4">
              <strong className="text-sm text-vscode-editor-foreground">Your choice:</strong>
              <select
                value={selected ?? ""}
                onChange={(e) => handleSelect(e.target.value)}
                className="mt-1 block w-full rounded-md border border-vscode-input-border px-3 py-2 text-sm"
              >
                <option value="">-- Select an option --</option>
                {OPTIONS.map((opt) => (
                  <option key={opt.id} value={opt.id}>
                    {opt.text}
                  </option>
                ))}
              </select>
            </div>
            <div className="text-xs text-vscode-editor-foreground/60 mb-4">
              Correct answer: <strong>
                {selected ? OPTIONS.find(o => o.id === selected)?.text ?? "None" : "None selected"}
              </strong>
            </div>
            <div className="flex gap-3">
              <button
                onClick={onCancel}
                className="flex-1 px-3 py-2 text-sm bg-vscode-input-background text-vscode-input-foreground rounded hover:bg-vscode-input-background/30 transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleVerify}
                disabled={!selected}
                className="flex-1 px-3 py-2 text-sm bg-vscode-button-background text-vscode-button-foreground rounded hover:bg-vscode-button-hoverBackground transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              >
                Verify
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
};