import type { DiagnosticItem } from "../../types/protocol";

export interface QuizOption {
  id: string;
  label: string;
}

export interface VerificationQuiz {
  questionId: string;
  question: string;
  options: QuizOption[];
  correctOptionId: string;
  explanation?: string;
  codeSnippet?: string;
}

const DISTRACTORS = [
  "Silence the finding with an inline suppression comment.",
  "Ignore it — the pattern is only a problem in production builds."
];

/**
 * Builds the comprehension question shown before a fix is applied.
 * Returns null when the diagnostic carries no remediation guidance, in which
 * case the verification step is skipped.
 */
export function buildVerificationQuiz(diagnostic: DiagnosticItem): VerificationQuiz | null {
  const remediation = diagnostic.recommendation?.trim();
  if (!remediation) return null;

  const correctOptionId = `${diagnostic.id}_correct`;
  const options: QuizOption[] = [
    { id: correctOptionId, label: remediation },
    ...DISTRACTORS.map((label, idx) => ({ id: `${diagnostic.id}_distractor_${idx}`, label }))
  ];

  return {
    questionId: diagnostic.id,
    question: `Before applying the fix: what is the correct way to resolve "${diagnostic.message}"?`,
    options,
    correctOptionId,
    explanation: diagnostic.title,
    codeSnippet: diagnostic.snippet
  };
}
