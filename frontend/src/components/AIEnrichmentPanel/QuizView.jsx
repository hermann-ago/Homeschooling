import React, { useState } from 'react';
import clsx from 'clsx';
import { CheckCircle2, XCircle, RefreshCw } from 'lucide-react';

export default function QuizView({ questions }) {
  const [answers, setAnswers] = useState({});
  const [submitted, setSubmitted] = useState(false);

  const score = submitted
    ? questions.filter((q, i) => answers[i] === q.answer).length
    : null;

  const handleSubmit = () => {
    if (Object.keys(answers).length < questions.length) return;
    setSubmitted(true);
  };

  const handleRetry = () => {
    setAnswers({});
    setSubmitted(false);
  };

  return (
    <div className="space-y-4">
      {submitted && (
        <div className={clsx(
          'rounded-xl p-4 text-center font-bold text-lg border',
          score === questions.length
            ? 'bg-action-soft border-line text-action'
            : score >= Math.ceil(questions.length / 2)
              ? 'bg-action-soft border-line text-action'
              : 'bg-problem-soft border-problem-soft text-problem'
        )}>
          {score === questions.length ? '🎉 Perfect!' : score >= Math.ceil(questions.length / 2) ? '👍 Good job!' : '💪 Keep studying!'}
          <span className="ml-2 font-normal text-sm">
            {score} / {questions.length} correct
          </span>
        </div>
      )}

      {questions.map((q, idx) => {
        const userAnswer = answers[idx];
        const isCorrect = submitted && userAnswer === q.answer;
        const isWrong = submitted && userAnswer && userAnswer !== q.answer;

        return (
          <div
            key={idx}
            className={clsx(
              'rounded-xl border p-4 transition',
              submitted
                ? isCorrect ? 'border-line bg-action-soft/50'
                  : isWrong ? 'border-problem-soft bg-problem-soft/50'
                    : 'border-border bg-white'
                : 'border-border bg-white'
            )}
          >
            <p className="font-semibold text-sm text-text-primary mb-3">
              <span className="text-action mr-1">{idx + 1}.</span> {q.question}
            </p>
            <div className="space-y-1.5">
              {q.choices.map((choice) => {
                const letter = choice.charAt(0);
                const isSelected = userAnswer === letter;
                const isAnswer = q.answer === letter;

                return (
                  <label
                    key={letter}
                    className={clsx(
                      'flex items-center space-x-2 px-3 py-2 rounded-lg cursor-pointer transition text-sm',
                      submitted
                        ? isAnswer
                          ? 'bg-action-soft text-action font-medium'
                          : isSelected && !isAnswer
                            ? 'bg-problem-soft text-problem'
                            : 'text-text-secondary'
                        : isSelected
                          ? 'bg-action-soft text-action'
                          : 'hover:bg-paper text-text-primary'
                    )}
                  >
                    <input
                      type="radio"
                      name={`q-${idx}`}
                      value={letter}
                      disabled={submitted}
                      checked={isSelected}
                      onChange={() => setAnswers(prev => ({ ...prev, [idx]: letter }))}
                      className="accent-[var(--color-action)]"
                    />
                    <span>{choice}</span>
                    {submitted && isAnswer && (
                      <CheckCircle2 className="w-3.5 h-3.5 text-action ml-auto shrink-0" />
                    )}
                    {submitted && isSelected && !isAnswer && (
                      <XCircle className="w-3.5 h-3.5 text-problem ml-auto shrink-0" />
                    )}
                  </label>
                );
              })}
            </div>
          </div>
        );
      })}

      <div className="flex gap-2">
        {!submitted ? (
          <button
            onClick={handleSubmit}
            disabled={Object.keys(answers).length < questions.length}
            className={clsx(
              'flex-1 py-2.5 rounded-xl text-sm font-bold transition',
              Object.keys(answers).length < questions.length
                ? 'bg-paper-deep text-subtle cursor-not-allowed'
                : 'bg-action hover:bg-action text-white active:scale-95'
            )}
          >
            Submit Quiz
          </button>
        ) : (
          <button
            onClick={handleRetry}
            className="flex items-center space-x-1.5 px-4 py-2 rounded-xl text-sm font-semibold bg-action-soft hover:bg-action-soft text-action transition"
          >
            <RefreshCw className="w-3.5 h-3.5" />
            <span>Try Again</span>
          </button>
        )}
      </div>
    </div>
  );
}
