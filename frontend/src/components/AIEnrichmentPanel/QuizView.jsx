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
            ? 'bg-green-50 border-green-200 text-green-700'
            : score >= Math.ceil(questions.length / 2)
              ? 'bg-amber-50 border-amber-200 text-amber-700'
              : 'bg-red-50 border-red-200 text-red-600'
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
                ? isCorrect ? 'border-green-200 bg-green-50/50'
                  : isWrong ? 'border-red-200 bg-red-50/50'
                    : 'border-border bg-white'
                : 'border-border bg-white'
            )}
          >
            <p className="font-semibold text-sm text-text-primary mb-3">
              <span className="text-violet-500 mr-1">{idx + 1}.</span> {q.question}
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
                          ? 'bg-green-100 text-green-700 font-medium'
                          : isSelected && !isAnswer
                            ? 'bg-red-100 text-red-600'
                            : 'text-text-secondary'
                        : isSelected
                          ? 'bg-violet-100 text-violet-700'
                          : 'hover:bg-gray-50 text-text-primary'
                    )}
                  >
                    <input
                      type="radio"
                      name={`q-${idx}`}
                      value={letter}
                      disabled={submitted}
                      checked={isSelected}
                      onChange={() => setAnswers(prev => ({ ...prev, [idx]: letter }))}
                      className="accent-violet-600"
                    />
                    <span>{choice}</span>
                    {submitted && isAnswer && (
                      <CheckCircle2 className="w-3.5 h-3.5 text-green-600 ml-auto flex-shrink-0" />
                    )}
                    {submitted && isSelected && !isAnswer && (
                      <XCircle className="w-3.5 h-3.5 text-red-500 ml-auto flex-shrink-0" />
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
                ? 'bg-gray-100 text-gray-400 cursor-not-allowed'
                : 'bg-violet-600 hover:bg-violet-700 text-white active:scale-95'
            )}
          >
            Submit Quiz
          </button>
        ) : (
          <button
            onClick={handleRetry}
            className="flex items-center space-x-1.5 px-4 py-2 rounded-xl text-sm font-semibold bg-violet-100 hover:bg-violet-200 text-violet-700 transition"
          >
            <RefreshCw className="w-3.5 h-3.5" />
            <span>Try Again</span>
          </button>
        )}
      </div>
    </div>
  );
}
