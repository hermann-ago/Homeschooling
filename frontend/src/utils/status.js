import { CheckCircle, TrendingUp, AlertCircle } from 'lucide-react';

/**
 * Get Tailwind classes for a progress status.
 */
export const getStatusColor = (status) => {
  switch (status) {
    case 'on_track': return 'text-green-600 bg-green-50 border-green-200';
    case 'behind': return 'text-yellow-600 bg-yellow-50 border-yellow-200';
    case 'at_risk': return 'text-red-600 bg-red-50 border-red-200';
    default: return 'text-gray-600 bg-gray-50 border-gray-200';
  }
};

/**
 * Get a human-readable label for a progress status.
 */
export const getStatusLabel = (status) => {
  switch (status) {
    case 'on_track': return 'On Track';
    case 'behind': return 'Slightly Behind';
    case 'at_risk': return 'At Risk';
    default: return 'Unknown';
  }
};

/**
 * Get an icon component for a progress status.
 */
export const getStatusIcon = (status) => {
  switch (status) {
    case 'on_track': return CheckCircle;
    case 'behind': return TrendingUp;
    case 'at_risk': return AlertCircle;
    default: return null;
  }
};
