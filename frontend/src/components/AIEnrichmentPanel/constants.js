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
    bg: 'bg-action-soft',
    border: 'border-line',
    text: 'text-action',
    btn: 'bg-action-soft hover:bg-action-soft text-action',
    badge: 'bg-action-soft text-action',
    icon: 'text-action',
  },
  sky: {
    bg: 'bg-action-soft',
    border: 'border-line',
    text: 'text-action',
    btn: 'bg-action-soft hover:bg-action-soft text-action',
    badge: 'bg-action-soft text-action',
    icon: 'text-action',
  },
  amber: {
    bg: 'bg-action-soft',
    border: 'border-line',
    text: 'text-action',
    btn: 'bg-action-soft hover:bg-action-soft text-action',
    badge: 'bg-action-soft text-action',
    icon: 'text-action',
  },
  emerald: {
    bg: 'bg-action-soft',
    border: 'border-line',
    text: 'text-action',
    btn: 'bg-action-soft hover:bg-action-soft text-action',
    badge: 'bg-action-soft text-action',
    icon: 'text-action',
  },
};
