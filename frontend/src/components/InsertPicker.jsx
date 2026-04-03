import React, { useState, useEffect } from 'react';
import { canvasApi } from '../api/canvas';
import { X, Search, BookOpen, ChevronRight } from 'lucide-react';
import clsx from 'clsx';

const InsertPicker = ({ childId, onSelect, onClose }) => {
  const [subjects, setSubjects] = useState([]);
  const [loading, setLoading] = useState(true);
  const [expandedSubject, setExpandedSubject] = useState(null);
  const [search, setSearch] = useState('');

  useEffect(() => {
    canvasApi.getAvailableTopics(childId)
      .then(data => {
        setSubjects(data);
        setLoading(false);
      })
      .catch(err => {
        console.error(err);
        setLoading(false);
      });
  }, [childId]);

  const filteredSubjects = subjects.map(s => ({
    ...s,
    topics: s.topics.filter(t =>
      t.title.toLowerCase().includes(search.toLowerCase()) ||
      s.subject_name.toLowerCase().includes(search.toLowerCase())
    ),
  })).filter(s => s.topics.length > 0);

  return (
    <div className="fixed inset-0 bg-black/50 backdrop-blur-sm flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-3xl w-full max-w-lg shadow-2xl overflow-hidden animate-in fade-in zoom-in duration-200 flex flex-col max-h-[80vh]">
        {/* Header */}
        <div className="p-5 border-b border-border flex justify-between items-center bg-gray-50 flex-shrink-0">
          <div>
            <h3 className="text-lg font-bold text-text-primary flex items-center">
              <BookOpen className="w-5 h-5 mr-2 text-accent" />
              Insert Pages
            </h3>
            <p className="text-xs text-text-secondary mt-0.5">Select a chapter from another book to insert.</p>
          </div>
          <button onClick={onClose} className="p-1.5 hover:bg-gray-200 rounded-lg transition">
            <X className="w-5 h-5 text-text-secondary" />
          </button>
        </div>

        {/* Search */}
        <div className="p-4 border-b border-border flex-shrink-0">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-text-secondary" />
            <input
              type="text"
              placeholder="Search topics..."
              className="w-full pl-9 pr-4 py-2.5 text-sm border border-border rounded-xl outline-none focus:border-accent focus:ring-2 focus:ring-accent/10 transition"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              autoFocus
            />
          </div>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-2">
          {loading ? (
            <div className="flex items-center justify-center p-8">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-accent"></div>
            </div>
          ) : filteredSubjects.length === 0 ? (
            <div className="text-center p-8 text-text-secondary text-sm">No topics found.</div>
          ) : (
            filteredSubjects.map(subject => (
              <div key={subject.subject_id} className="mb-1">
                <button
                  onClick={() => setExpandedSubject(
                    expandedSubject === subject.subject_id ? null : subject.subject_id
                  )}
                  className="w-full flex items-center justify-between p-3 rounded-xl hover:bg-gray-50 transition text-left"
                >
                  <span className="font-semibold text-sm text-text-primary">{subject.subject_name}</span>
                  <div className="flex items-center space-x-2">
                    <span className="text-xs text-text-secondary bg-gray-100 px-2 py-0.5 rounded-full">
                      {subject.topics.length} topics
                    </span>
                    <ChevronRight className={clsx(
                      "w-4 h-4 text-text-secondary transition-transform",
                      expandedSubject === subject.subject_id && "rotate-90"
                    )} />
                  </div>
                </button>

                {expandedSubject === subject.subject_id && (
                  <div className="ml-4 pl-3 border-l-2 border-accent/20 space-y-0.5 pb-2">
                    {subject.topics.map(topic => (
                      <button
                        key={topic.id}
                        onClick={() => onSelect(topic)}
                        className="w-full text-left p-2.5 rounded-lg hover:bg-accent/5 transition group flex items-center justify-between"
                      >
                        <div className="min-w-0">
                          <div className="text-sm text-text-primary truncate group-hover:text-accent transition">
                            {topic.title}
                          </div>
                          <div className="text-[10px] text-text-secondary">
                            Pages {topic.page_start}–{topic.page_end}
                            {topic.pdf_filename && (
                              <span className="ml-1 opacity-60">· {topic.pdf_filename}</span>
                            )}
                          </div>
                        </div>
                        <span className="text-xs text-accent opacity-0 group-hover:opacity-100 transition font-medium ml-2 whitespace-nowrap">
                          Insert →
                        </span>
                      </button>
                    ))}
                  </div>
                )}
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
};

export default InsertPicker;
