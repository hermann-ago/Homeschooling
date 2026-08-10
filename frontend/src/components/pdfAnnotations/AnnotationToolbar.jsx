import React from 'react';
import {
  Check,
  CircleAlert,
  Eraser,
  Hand,
  Loader2,
  PenLine,
  Redo2,
  RotateCcw,
  Trash2,
  Undo2,
  ZoomIn,
  ZoomOut,
} from 'lucide-react';
import clsx from 'clsx';


const COLORS = ['#111827', '#1D4ED8', '#DC2626', '#15803D', '#EA580C'];
const WIDTHS = [
  { label: 'Thin', value: 0.0025, size: 4 },
  { label: 'Medium', value: 0.005, size: 7 },
  { label: 'Thick', value: 0.009, size: 11 },
];


const AnnotationToolbar = ({
  tool,
  setTool,
  color,
  setColor,
  strokeWidth,
  setStrokeWidth,
  zoom,
  setZoom,
  saveStatus,
  canUndo,
  canRedo,
  hasStrokes,
  onUndo,
  onRedo,
  onClear,
  onRetry,
}) => {
  const toolButton = (name, label, iconComponent) => (
    <button
      type="button"
      aria-label={label}
      aria-pressed={tool === name}
      title={label}
      onClick={() => setTool(name)}
      className={clsx(
        'w-11 h-11 rounded-xl flex items-center justify-center flex-shrink-0 transition active:scale-95',
        tool === name ? 'bg-accent text-white shadow-sm' : 'bg-white text-text-secondary hover:bg-gray-100',
      )}
    >
      {React.createElement(iconComponent, { className: 'w-5 h-5' })}
    </button>
  );

  const status = {
    loading: { icon: Loader2, label: 'Loading notes', className: 'animate-spin text-text-secondary' },
    saving: { icon: Loader2, label: 'Saving', className: 'animate-spin text-accent' },
    saved: { icon: Check, label: 'Saved', className: 'text-green-600' },
    unsaved: { icon: RotateCcw, label: 'Waiting to save', className: 'text-amber-600' },
    error: { icon: CircleAlert, label: 'Not saved', className: 'text-red-600' },
    conflict: { icon: CircleAlert, label: 'Save conflict', className: 'text-amber-700' },
  }[saveStatus] || { icon: Check, label: 'Saved', className: 'text-green-600' };
  const StatusIcon = status.icon;

  return (
    <div className="border-b border-border bg-gray-50/95 backdrop-blur flex-shrink-0">
      <div className="px-2 py-2 flex items-center gap-1.5 overflow-x-auto custom-scrollbar">
        {toolButton('hand', 'Pan and scroll', Hand)}
        {toolButton('pen', 'Draw with pen', PenLine)}
        {toolButton('eraser', 'Erase complete strokes', Eraser)}
        <div className="w-px h-8 bg-border flex-shrink-0 mx-0.5" />
        <button type="button" aria-label="Undo" title="Undo" disabled={!canUndo} onClick={onUndo} className="w-11 h-11 rounded-xl bg-white flex items-center justify-center disabled:opacity-30 flex-shrink-0"><Undo2 className="w-5 h-5" /></button>
        <button type="button" aria-label="Redo" title="Redo" disabled={!canRedo} onClick={onRedo} className="w-11 h-11 rounded-xl bg-white flex items-center justify-center disabled:opacity-30 flex-shrink-0"><Redo2 className="w-5 h-5" /></button>
        <button type="button" aria-label="Clear this page" title="Clear this page" disabled={!hasStrokes} onClick={onClear} className="w-11 h-11 rounded-xl bg-white text-red-500 flex items-center justify-center disabled:opacity-30 flex-shrink-0"><Trash2 className="w-5 h-5" /></button>
        <div className="w-px h-8 bg-border flex-shrink-0 mx-0.5" />
        <button type="button" aria-label="Zoom out" title="Zoom out" disabled={zoom <= 75} onClick={() => setZoom((value) => Math.max(75, value - 25))} className="w-11 h-11 rounded-xl bg-white flex items-center justify-center disabled:opacity-30 flex-shrink-0"><ZoomOut className="w-5 h-5" /></button>
        <span className="text-xs font-bold text-text-secondary min-w-11 text-center flex-shrink-0">{zoom}%</span>
        <button type="button" aria-label="Zoom in" title="Zoom in" disabled={zoom >= 250} onClick={() => setZoom((value) => Math.min(250, value + 25))} className="w-11 h-11 rounded-xl bg-white flex items-center justify-center disabled:opacity-30 flex-shrink-0"><ZoomIn className="w-5 h-5" /></button>
        <div className="ml-auto flex items-center gap-1.5 px-2 text-xs font-semibold whitespace-nowrap flex-shrink-0">
          <StatusIcon className={clsx('w-4 h-4', status.className)} />
          <span className="text-text-secondary">{status.label}</span>
          {saveStatus === 'error' && <button type="button" onClick={onRetry} className="text-accent underline">Retry</button>}
        </div>
      </div>

      {tool === 'pen' && (
        <div className="px-3 pb-2 flex items-center gap-2 overflow-x-auto">
          <span className="text-[10px] font-bold uppercase tracking-wide text-text-secondary flex-shrink-0">Color</span>
          {COLORS.map((preset) => (
            <button
              key={preset}
              type="button"
              aria-label={`Use ${preset}`}
              aria-pressed={color.toLowerCase() === preset.toLowerCase()}
              onClick={() => setColor(preset)}
              className={clsx('w-8 h-8 rounded-full border-2 flex-shrink-0', color.toLowerCase() === preset.toLowerCase() ? 'border-accent ring-2 ring-accent/20' : 'border-white shadow')}
              style={{ backgroundColor: preset }}
            />
          ))}
          <label className="relative w-8 h-8 rounded-full border-2 border-white shadow overflow-hidden flex-shrink-0" title="Custom color" style={{ backgroundColor: color }}>
            <span className="sr-only">Custom color</span>
            <input type="color" value={color} onChange={(event) => setColor(event.target.value)} className="absolute inset-0 opacity-0 cursor-pointer" />
          </label>
          <div className="w-px h-6 bg-border flex-shrink-0 mx-1" />
          <span className="text-[10px] font-bold uppercase tracking-wide text-text-secondary flex-shrink-0">Size</span>
          {WIDTHS.map((widthOption) => (
            <button
              key={widthOption.label}
              type="button"
              aria-label={`${widthOption.label} pen`}
              aria-pressed={strokeWidth === widthOption.value}
              onClick={() => setStrokeWidth(widthOption.value)}
              className={clsx('w-10 h-8 rounded-lg flex items-center justify-center flex-shrink-0', strokeWidth === widthOption.value ? 'bg-accent/15 ring-1 ring-accent' : 'bg-white')}
            >
              <span className="rounded-full bg-text-primary" style={{ width: widthOption.size, height: widthOption.size }} />
            </button>
          ))}
        </div>
      )}
    </div>
  );
};


export default AnnotationToolbar;
