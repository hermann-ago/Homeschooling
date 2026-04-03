import React from 'react';
import { X } from 'lucide-react';

/**
 * Reusable confirmation dialog to replace window.confirm().
 * 
 * Props:
 * - open: boolean
 * - title: string
 * - message: string
 * - confirmLabel: string (default: "Confirm")
 * - cancelLabel: string (default: "Cancel")
 * - variant: "danger" | "default" (default: "default")
 * - onConfirm: () => void
 * - onCancel: () => void
 */
const ConfirmDialog = ({ 
  open, title, message, 
  confirmLabel = 'Confirm', 
  cancelLabel = 'Cancel',
  variant = 'default',
  onConfirm, onCancel 
}) => {
  if (!open) return null;

  const confirmClasses = variant === 'danger'
    ? 'bg-red-600 hover:bg-red-700 text-white'
    : 'bg-accent hover:bg-accent-hover text-white';

  return (
    <div className="fixed inset-0 bg-black/50 backdrop-blur-sm flex items-center justify-center z-[60] p-4">
      <div className="bg-white rounded-2xl w-full max-w-md shadow-2xl overflow-hidden animate-in fade-in zoom-in duration-200">
        <div className="p-6 border-b border-border flex justify-between items-center">
          <h3 className="text-lg font-bold text-text-primary">{title}</h3>
          <button onClick={onCancel} className="p-1 text-text-secondary hover:text-text-primary">
            <X className="w-5 h-5" />
          </button>
        </div>
        <div className="p-6">
          <p className="text-text-secondary text-sm">{message}</p>
        </div>
        <div className="p-4 bg-gray-50 flex justify-end space-x-3">
          <button 
            onClick={onCancel}
            className="px-4 py-2 text-sm font-medium text-text-secondary hover:text-text-primary transition"
          >
            {cancelLabel}
          </button>
          <button 
            onClick={onConfirm}
            className={`px-5 py-2 rounded-xl font-bold text-sm shadow-sm transition ${confirmClasses}`}
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
};

export default ConfirmDialog;
