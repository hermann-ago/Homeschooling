import React from 'react';
import { Lightbulb } from 'lucide-react';

export default function ExplainView({ text }) {
  return (
    <div className="bg-white rounded-xl border border-emerald-200 p-5">
      <div className="flex items-center space-x-2 mb-3">
        <Lightbulb className="w-4 h-4 text-emerald-500" />
        <span className="text-xs font-semibold text-emerald-600 uppercase tracking-wide">
          Simple Explanation
        </span>
      </div>
      <p className="text-sm text-text-primary leading-relaxed">{text}</p>
    </div>
  );
}
