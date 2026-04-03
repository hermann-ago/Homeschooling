import React, { useState } from 'react';
import { X } from 'lucide-react';

/**
 * Reusable input prompt dialog to replace window.prompt().
 * 
 * Props:
 * - open: boolean
 * - title: string
 * - label: string
 * - placeholder: string
 * - defaultValue: string
 * - submitLabel: string (default: "Submit")
 * - onSubmit: (value: string) => void
 * - onCancel: () => void
 */
const InputDialog = ({ 
  open, title, label, placeholder = '', defaultValue = '',
  submitLabel = 'Submit',
  onSubmit, onCancel 
}) => {
  const [value, setValue] = useState(defaultValue);

  if (!open) return null;

  const handleSubmit = (e) => {
    e.preventDefault();
    if (value.trim()) {
      onSubmit(value.trim());
      setValue('');
    }
  };

  return (
    <div className="fixed inset-0 bg-black/50 backdrop-blur-sm flex items-center justify-center z-[60] p-4">
      <div className="bg-white rounded-2xl w-full max-w-md shadow-2xl overflow-hidden animate-in fade-in zoom-in duration-200">
        <div className="p-6 border-b border-border flex justify-between items-center">
          <h3 className="text-lg font-bold text-text-primary">{title}</h3>
          <button onClick={onCancel} className="p-1 text-text-secondary hover:text-text-primary">
            <X className="w-5 h-5" />
          </button>
        </div>
        <form onSubmit={handleSubmit} className="p-6 space-y-4">
          {label && (
            <label className="block text-sm font-semibold text-text-secondary">{label}</label>
          )}
          <input
            type="text"
            autoFocus
            className="w-full px-4 py-2 border border-border rounded-lg outline-none focus:ring-2 focus:ring-accent/20 focus:border-accent"
            placeholder={placeholder}
            value={value}
            onChange={(e) => setValue(e.target.value)}
          />
          <div className="flex justify-end space-x-3 pt-2">
            <button 
              type="button"
              onClick={onCancel}
              className="px-4 py-2 text-sm font-medium text-text-secondary hover:text-text-primary transition"
            >
              Cancel
            </button>
            <button 
              type="submit"
              disabled={!value.trim()}
              className="bg-accent text-white px-5 py-2 rounded-xl font-bold text-sm shadow-sm hover:bg-accent-hover transition disabled:opacity-50"
            >
              {submitLabel}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

export default InputDialog;
