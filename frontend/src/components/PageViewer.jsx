import React from 'react';
import { X, ExternalLink } from 'lucide-react';
import { API_BASE_URL } from '../api/client';

const PageViewer = ({ slot, onClose }) => {
  if (!slot || !slot.pdf_path) return null;

  const startPage = slot.page_from || 1;
  const endPage = slot.page_to || startPage;
  
  const bookPageOffset = slot.pdf_page_offset || 0;
  const physicalStart = startPage + bookPageOffset;
  const physicalEnd = endPage + bookPageOffset;

  // The backend will create a tiny PDF slice perfectly constrained 
  // to exactly the assigned pages for this checklist task.
  const slicedPdfUrl = `${API_BASE_URL}/pdf/slice?path=${encodeURIComponent(slot.pdf_path)}&start=${physicalStart}&end=${physicalEnd}#view=FitH`;

  const handleOpenExternal = () => {
    window.open(slicedPdfUrl, '_blank');
  };

  return (
    <div className="flex flex-col h-full bg-surface">
      {/* Header */}
      <div className="flex items-center justify-between p-4 border-b border-border bg-gray-50 flex-shrink-0">
        <div>
          <h3 className="font-bold text-text-primary text-sm line-clamp-1" title={slot.subject_name}>
            {slot.subject_name}
          </h3>
          <p className="text-xs text-text-secondary line-clamp-1" title={slot.topic_title}>
            {slot.topic_title}
          </p>
          <p className="text-xs text-text-secondary mt-0.5 font-medium">
            Assigned: Pages {startPage} - {endPage}
          </p>
        </div>
        <div className="flex items-center space-x-2">
          <button 
            onClick={handleOpenExternal}
            className="p-1.5 text-text-secondary hover:text-text-primary hover:bg-gray-200 rounded-md transition"
            title="Open explicitly in new tab for fullscreen viewing/printing"
          >
            <ExternalLink className="w-4 h-4" />
          </button>
          <button 
            onClick={onClose}
            className="p-1.5 text-text-secondary hover:text-text-primary hover:bg-gray-200 rounded-md transition"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* Viewer Body */}
      <div className="flex-1 bg-gray-100 flex flex-col relative">
        <iframe
          src={slicedPdfUrl}
          title="PDF Viewer"
          className="w-full h-full border-none"
        />
      </div>
    </div>
  );
};

export default PageViewer;
