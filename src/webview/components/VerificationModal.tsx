import React, { useState } from 'react';

interface QuizProps {
  quiz: {
    question: string;
    options: string[];
    correct_index: number;
    explanation: string;
  };
  suggestedFix: string;
  onApplyFix: (fixCode: string) => void;
}

export const VerificationModal: React.FC<QuizProps> = ({ quiz, suggestedFix, onApplyFix }) => {
  const [selectedIdx, setSelectedIdx] = useState<number | null>(null);
  const isCorrect = selectedIdx === quiz.correct_index;

  return (
    <div style={{ background: '#1e293b', padding: '12px', borderRadius: '8px', color: '#f8fafc', marginTop: '12px' }}>
      <h4 style={{ fontSize: '12px', fontWeight: 'bold', marginBottom: '8px' }}>Comprehension Verification Check</h4>
      <p style={{ fontSize: '11px', color: '#cbd5e1', marginBottom: '8px' }}>{quiz.question}</p>

      {quiz.options.map((opt, idx) => (
        <button
          key={idx}
          onClick={() => setSelectedIdx(idx)}
          style={{
            display: 'block',
            width: '100%',
            textAlign: 'left',
            padding: '6px 8px',
            margin: '4px 0',
            fontSize: '11px',
            borderRadius: '4px',
            border: '1px solid #334155',
            background: selectedIdx === idx ? (idx === quiz.correct_index ? '#16a34a' : '#dc2626') : '#0f172a',
            color: '#ffffff',
            cursor: 'pointer'
          }}
        >
          {opt}
        </button>
      ))}

      <button
        disabled={!isCorrect}
        onClick={() => onApplyFix(suggestedFix)}
        style={{
          marginTop: '10px',
          width: '100%',
          padding: '8px',
          fontSize: '11px',
          fontWeight: 'bold',
          borderRadius: '4px',
          background: isCorrect ? '#4f46e5' : '#334155',
          color: '#ffffff',
          cursor: isCorrect ? 'pointer' : 'not-allowed',
          opacity: isCorrect ? 1 : 0.5
        }}
      >
        {isCorrect ? 'Apply Verified Fix to Editor' : 'Pass Verification Quiz to Unlock Fix'}
      </button>
    </div>
  );
};