import React, { useState } from 'react';
import clsx from 'clsx';

export default function TermsView({ terms }) {
  const [flipped, setFlipped] = useState({});

  const toggle = (idx) => setFlipped(prev => ({ ...prev, [idx]: !prev[idx] }));

  return (
    <div className="grid grid-cols-1 gap-3">
      {terms.map((item, idx) => (
        <button
          key={idx}
          onClick={() => toggle(idx)}
          className={clsx(
            'text-left rounded-xl border p-4 transition cursor-pointer active:scale-95',
            flipped[idx]
              ? 'bg-action-soft border-line'
              : 'bg-white border-border hover:border-line hover:bg-action-soft/30'
          )}
        >
          <div className="text-xs text-action font-semibold uppercase tracking-wide mb-1">
            {flipped[idx] ? 'Definition' : 'Term  — tap to reveal'}
          </div>
          <div className={clsx(
            'text-sm font-medium',
            flipped[idx] ? 'text-action' : 'text-text-primary'
          )}>
            {flipped[idx] ? item.definition : item.term}
          </div>
        </button>
      ))}
    </div>
  );
}
