import { BrainCircuit, Volume2, BookMarked, Lightbulb } from 'lucide-react';

export const TOOLS = [
  {
    key: 'quiz',
    label: 'Quiz',
    icon: BrainCircuit,
    color: 'violet',
    description: 'Test your knowledge',
  },
  {
    key: 'audio',
    label: 'Listen',
    icon: Volume2,
    color: 'sky',
    description: 'Hear a summary',
  },
  {
    key: 'terms',
    label: 'Key Terms',
    icon: BookMarked,
    color: 'amber',
    description: 'Learn vocabulary',
  },
  {
    key: 'explain',
    label: 'Simplify',
    icon: Lightbulb,
    color: 'emerald',
    description: 'Explain simply',
  },
];

export const COLOUR = {
  violet: {
    bg: 'bg-violet-50',
    border: 'border-violet-200',
    text: 'text-violet-700',
    btn: 'bg-violet-100 hover:bg-violet-200 text-violet-700',
    badge: 'bg-violet-100 text-violet-600',
    icon: 'text-violet-500',
  },
  sky: {
    bg: 'bg-sky-50',
    border: 'border-sky-200',
    text: 'text-sky-700',
    btn: 'bg-sky-100 hover:bg-sky-200 text-sky-700',
    badge: 'bg-sky-100 text-sky-600',
    icon: 'text-sky-500',
  },
  amber: {
    bg: 'bg-amber-50',
    border: 'border-amber-200',
    text: 'text-amber-700',
    btn: 'bg-amber-100 hover:bg-amber-200 text-amber-700',
    badge: 'bg-amber-100 text-amber-600',
    icon: 'text-amber-500',
  },
  emerald: {
    bg: 'bg-emerald-50',
    border: 'border-emerald-200',
    text: 'text-emerald-700',
    btn: 'bg-emerald-100 hover:bg-emerald-200 text-emerald-700',
    badge: 'bg-emerald-100 text-emerald-600',
    icon: 'text-emerald-500',
  },
};
