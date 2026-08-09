import React, { useState, useEffect, useRef } from 'react';
import { subjectsApi } from '../api/subjects';
import { UploadCloud, FileText, ChevronDown, ChevronRight, Edit3, Loader2, BookOpen, CheckCircle2, Circle, Trash2, Star, Book, X } from 'lucide-react';
import PageViewer from '../components/PageViewer';
import clsx from 'clsx';

const Curriculum = ({ activeChildId }) => {
  const [subjects, setSubjects] = useState([]);
  const [expandedSubject, setExpandedSubject] = useState(null);
  const [topics, setTopics] = useState({});
  const [selectedBook, setSelectedBook] = useState({}); // { subjectId: pdf_filename }
  const [selectedTopicForViewer, setSelectedTopicForViewer] = useState(null);
  const [isUploading, setIsUploading] = useState(false);
  const [editingSubject, setEditingSubject] = useState(null);
  const [chaptersCount, setChaptersCount] = useState(1);
  const [generating, setGenerating] = useState(false);
  const fileInputRef = useRef(null);
  
  const loadSubjects = () => {
    if (!activeChildId) return;
    subjectsApi.getByChildId(activeChildId).then(setSubjects).catch(console.error);
  };

  useEffect(() => {
    loadSubjects();
    setExpandedSubject(null);
    setTopics({});
    setSelectedBook({});
  }, [activeChildId]);

  const loadTopics = async (subjectId) => {
    try {
      const data = await subjectsApi.getTopics(subjectId);
      setTopics(prev => ({ ...prev, [subjectId]: data }));
      
      if (data.length > 0) {
        // Group by book to find the main one
        const mainBook = data.find(t => t.is_core);
        const defaultFilename = mainBook ? mainBook.pdf_filename : data[0].pdf_filename;
        const bookName = defaultFilename || 'Unknown Book';
        setSelectedBook(prev => ({ ...prev, [subjectId]: bookName }));
      }
    } catch (e) {
      console.error(e);
    }
  };

  const toggleSubject = (subjectId) => {
    if (expandedSubject === subjectId) {
      setExpandedSubject(null);
    } else {
      setExpandedSubject(subjectId);
      if (!topics[subjectId]) {
        loadTopics(subjectId);
      }
    }
  };

  const handleUpload = async (subjectId, file) => {
    if (!file) return;
    setIsUploading(subjectId);
    try {
      await subjectsApi.uploadPdf(subjectId, file);
      await loadTopics(subjectId);
      alert('PDF analyzed and curriculum updated successfully!');
    } catch (error) {
      alert(`Upload failed: ${error.message}`);
    } finally {
      setIsUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  };

  const handleToggleComplete = async (subjectId, topicId) => {
    try {
      const updated = await subjectsApi.toggleTopicComplete(subjectId, topicId);
      setTopics(prev => ({
        ...prev,
        [subjectId]: prev[subjectId].map(t =>
          t.id === topicId ? { ...t, completed: updated.completed } : t
        ),
      }));
    } catch (e) {
      alert('Failed to toggle topic completion: ' + e.message);
    }
  };

  const handleCompletePrevious = async (subjectId, topicId) => {
    if (!window.confirm("Action required: This will mark this topic and ALL previous topics as completed. This is helpful to 'catch up' to your current chapter. Continue?")) return;
    try {
      await subjectsApi.completePrevious(subjectId, topicId);
      await loadTopics(subjectId);
    } catch (error) {
      alert("Failed to update topics: " + error.message);
    }
  };

  const handleAddSubject = async () => {
    if (!activeChildId) return alert('Select a child first.');
    const name = window.prompt("Enter new subject name (e.g., Math, Science):");
    if (!name) return;
    try {
      await subjectsApi.create({ name, weight: 1.0, child_id: activeChildId });
      loadSubjects();
    } catch (e) {
      alert("Failed to create subject: " + e.message);
    }
  };

  const handleDeleteSubject = async (e, subjectId, subjectName) => {
    e.stopPropagation();
    if (!window.confirm(`Are you sure you want to delete ${subjectName}? This will permanently remove all topics and scheduled activities.`)) return;
    try {
      await subjectsApi.deleteSubject(subjectId);
      loadSubjects();
      if (expandedSubject === subjectId) setExpandedSubject(null);
    } catch (err) {
      alert("Failed to delete subject: " + err.message);
    }
  };

  const handleDeleteTopic = async (e, subjectId, topicId, topicTitle) => {
    e.stopPropagation();
    if (!window.confirm(`Are you sure you want to delete "${topicTitle}"? This will permanently remove any scheduled activities for it.`)) return;
    try {
      await subjectsApi.deleteTopic(subjectId, topicId);
      loadTopics(subjectId);
    } catch (err) {
      alert("Failed to delete topic: " + err.message);
    }
  };

  const handleSetMainBook = async (subjectId, filename) => {
    if (filename === 'Unknown Book') return;
    try {
      await subjectsApi.setMainBook(subjectId, filename);
      loadTopics(subjectId);
    } catch (e) {
      alert("Failed to set main book: " + e.message);
    }
  };

  const handleDeleteBook = async (subjectId, filename) => {
    if (filename === 'Unknown Book') return;
    if (!window.confirm(`Are you sure you want to delete the book "${filename}"? All its topics and schedule slots will be permanently removed.`)) return;
    try {
      await subjectsApi.deleteBook(subjectId, filename);
      loadTopics(subjectId);
    } catch (e) {
      alert("Failed to delete book: " + e.message);
    }
  };

  return (
    <div className="flex h-full w-full overflow-hidden">
        <div className="p-4 sm:p-6 lg:p-8 overflow-y-auto w-full transition-all duration-300">
        <header className="mb-6 sm:mb-10 flex flex-col sm:flex-row justify-between sm:items-end gap-4">
        <div>
          <h1 className="text-2xl sm:text-3xl font-bold text-text-primary mb-2">Curriculum</h1>
          <p className="text-text-secondary text-sm sm:text-base">Upload PDFs to manage the main curriculum and accessory books.</p>
        </div>
        <button 
          onClick={handleAddSubject}
          className="bg-text-primary text-white py-2 px-4 rounded-lg text-sm font-medium hover:bg-gray-800 transition shadow-sm"
        >
          + Add Subject
        </button>
      </header>

      {subjects.length === 0 ? (
        <div className="bg-surface rounded-xl border border-border p-12 text-center shadow-soft">
          <BookOpen className="w-12 h-12 text-gray-300 mx-auto mb-4" />
          <h3 className="text-lg font-medium text-text-primary">No subjects found</h3>
          <p className="text-text-secondary mt-1">Add a subject in Settings to start uploading curriculum.</p>
        </div>
      ) : (
        <div className="space-y-4">
          {subjects.map(subject => {
            const isExpanded = expandedSubject === subject.id;
            const subjectTopics = topics[subject.id] || [];
            
            // Derive unique books for this subject
            const booksMap = new Map();
            subjectTopics.forEach(t => {
              const fn = t.pdf_filename || 'Unknown Book';
              if (!booksMap.has(fn)) {
                booksMap.set(fn, { filename: fn, is_core: !!t.is_core, topicCount: 1 });
              } else {
                const book = booksMap.get(fn);
                book.is_core = book.is_core || !!t.is_core;
                book.topicCount++;
              }
            });
            const books = Array.from(booksMap.values());
            
            const currentBookFilename = selectedBook[subject.id];
            const currentBookTopics = subjectTopics.filter(t => (t.pdf_filename || 'Unknown Book') === currentBookFilename);
            const currentBookInfo = books.find(b => b.filename === currentBookFilename);

            // Calculate if there are multiple core books (defensive)
            const coreBooksCount = books.filter(b => b.is_core).length;

            return (
              <div key={subject.id} className="bg-surface border border-border rounded-xl shadow-soft overflow-hidden transition-all duration-200">
                {/* Subject Header Row */}
                <div 
                  className="flex items-center justify-between p-4 cursor-pointer hover:bg-gray-50 bg-white z-10 relative"
                  onClick={() => toggleSubject(subject.id)}
                >
                  <div className="flex items-center">
                    <div className="mr-4 text-text-secondary">
                      {isExpanded ? <ChevronDown className="w-5 h-5" /> : <ChevronRight className="w-5 h-5" />}
                    </div>
                    <div className="font-bold text-xl text-text-primary">{subject.name}</div>
                  </div>
                  <div className="flex items-center space-x-2">
                    <span className="text-sm font-medium bg-gray-100 text-gray-600 px-3 py-1 rounded-full whitespace-nowrap">
                      Weight: {subject.weight}x
                    </span>
                    <button 
                      onClick={(e) => {
                        e.stopPropagation();
                        if (!topics[subject.id]) { loadTopics(subject.id); }
                        setEditingSubject({ ...subject, end_date: subject.end_date || '', slot_type: subject.slot_type || 'A' });
                      }}
                      className="p-1.5 text-text-secondary hover:text-accent hover:bg-accent/10 rounded-md transition"
                      title="Edit Subject"
                    >
                      <Edit3 className="w-4 h-4" />
                    </button>
                    <button 
                      onClick={(e) => handleDeleteSubject(e, subject.id, subject.name)}
                      className="p-1.5 text-text-secondary hover:text-red-500 hover:bg-red-50 rounded-md transition"
                      title="Delete Subject"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>
                </div>

                {/* Expanded Content: Split View */}
                {isExpanded && (
                  <div className="border-t border-border bg-gray-50/30 flex flex-col md:flex-row min-h-[400px]">
                    
                    {/* LEFT COLUMN: Books List */}
                    <div className="w-full md:w-64 lg:w-72 border-b md:border-b-0 md:border-r border-border bg-white flex flex-col">
                      <div className="px-4 py-3 border-b border-border bg-gray-50/50 flex justify-between items-center">
                        <h4 className="font-semibold text-text-primary text-sm uppercase tracking-wider">Books ({books.length})</h4>
                        <div>
                          <input 
                            type="file" 
                            id={`pdf-upload-${subject.id}`} 
                            className="hidden" 
                            accept=".pdf"
                            ref={fileInputRef}
                            onChange={(e) => handleUpload(subject.id, e.target.files[0])}
                            disabled={isUploading === subject.id}
                          />
                          <label 
                            htmlFor={`pdf-upload-${subject.id}`}
                            title="Upload Book PDF"
                            className={clsx(
                              "flex items-center justify-center p-1.5 rounded-md text-sm transition cursor-pointer border",
                              isUploading === subject.id
                                ? "bg-gray-100 text-gray-500 border-gray-200 cursor-not-allowed"
                                : "bg-white text-text-secondary border-border hover:border-accent hover:text-accent shadow-sm"
                            )}
                          >
                            {isUploading === subject.id ? (
                              <Loader2 className="w-4 h-4 animate-spin" />
                            ) : (
                              <UploadCloud className="w-4 h-4" />
                            )}
                          </label>
                        </div>
                      </div>
                      
                      <div className="flex-1 overflow-y-auto p-3 space-y-1">
                        {books.length === 0 ? (
                          <div className="text-center p-4 text-sm text-text-secondary">
                            No books added yet.
                          </div>
                        ) : (
                          books.map(book => (
                            <button
                              key={book.filename}
                              onClick={() => setSelectedBook(prev => ({...prev, [subject.id]: book.filename}))}
                              className={clsx(
                                "w-full text-left px-3 py-2.5 rounded-lg text-sm font-medium transition flex items-start justify-between group",
                                currentBookFilename === book.filename 
                                  ? "bg-accent/10 text-accent" 
                                  : "text-text-secondary hover:bg-gray-100 hover:text-text-primary"
                              )}
                            >
                              <div className="flex items-start min-w-0 pr-2">
                                <BookOpen className={clsx("w-4 h-4 mr-2 flex-shrink-0 mt-0.5", currentBookFilename === book.filename ? "text-accent" : "text-gray-400")} />
                                <div className="truncate flex flex-col">
                                  <span className="truncate leading-tight">{book.filename}</span>
                                  <span className="text-[10px] font-normal opacity-70 mt-0.5">{book.topicCount} topics</span>
                                </div>
                              </div>
                              {book.is_core && (
                                <Star className="w-4 h-4 fill-accent text-accent flex-shrink-0" title="Main Curriculum Book" />
                              )}
                            </button>
                          ))
                        )}
                      </div>
                      

                    </div>

                    {/* RIGHT COLUMN: Topics View */}
                    <div className="flex-1 bg-gray-50/30 flex flex-col min-w-0">
                      {!currentBookInfo ? (
                        <div className="flex-1 flex flex-col items-center justify-center p-8 text-text-secondary text-center">
                          <FileText className="w-12 h-12 text-gray-300 mb-3" />
                          <p>Select a book from the left to view its chapters.</p>
                          <p className="text-sm mt-1">Or upload a PDF to automatically generate the curriculum structure.</p>
                        </div>
                      ) : (
                        <>
                          <div className="p-6 border-b border-border bg-white flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                            <div>
                              <h3 className="text-lg font-bold text-text-primary flex items-center mb-1">
                                {currentBookInfo.filename}
                              </h3>
                              <p className="text-sm text-text-secondary border border-border bg-gray-50 rounded px-2 py-0.5 inline-flex items-center">
                                {currentBookInfo.is_core ? (
                                  <><Star className="w-3 h-3 mr-1 fill-accent text-accent" /> Main Curriculum</>
                                ) : (
                                  "Accessory Book (Not Scheduled)"
                                )}
                              </p>
                              {currentBookInfo.filename !== 'Unknown Book' && (
                                <p className="text-sm text-text-secondary border border-border bg-gray-50 rounded px-2 py-0.5 inline-flex items-center ml-2">
                                  Offset: {currentBookTopics.length > 0 ? currentBookTopics[0].pdf_page_offset || 0 : 0}
                                </p>
                              )}
                            </div>
                            
                            <div className="flex items-center space-x-2 self-start sm:self-auto">
                              {(!currentBookInfo.is_core || coreBooksCount > 1) && currentBookInfo.filename !== 'Unknown Book' && (
                                <button
                                  onClick={() => handleSetMainBook(subject.id, currentBookInfo.filename)}
                                  className="flex items-center px-4 py-2 bg-accent text-white hover:bg-accent-hover text-sm font-semibold rounded-lg transition shadow-sm"
                                >
                                  <Star className="w-4 h-4 mr-1.5 fill-white" />
                                  Set as Main
                                </button>
                              )}
                              
                              {currentBookInfo.filename !== 'Unknown Book' && (
                                <button
                                  onClick={() => handleDeleteBook(subject.id, currentBookInfo.filename)}
                                  className="flex items-center px-3 py-1.5 text-text-secondary hover:text-red-600 hover:bg-red-50 text-sm font-medium rounded-md transition border border-transparent hover:border-red-100"
                                >
                                  <Trash2 className="w-4 h-4 mr-1.5" />
                                  Delete Book
                                </button>
                              )}
                            </div>
                          </div>

                          <div className="p-6 bg-gray-50/50 flex-1">
                            <div className="bg-surface rounded-lg border border-border overflow-hidden shadow-sm">
                              <div className="overflow-x-auto">
                                <table className="min-w-full divide-y divide-border">
                                  <thead className="bg-gray-50">
                                    <tr>
                                      <th className="px-4 py-3 text-center text-xs font-medium text-text-secondary uppercase tracking-wider w-12">Done</th>
                                      <th className="px-6 py-3 text-left text-xs font-medium text-text-secondary uppercase tracking-wider">Chapter / Topic</th>
                                      <th className="px-6 py-3 text-center text-xs font-medium text-text-secondary uppercase tracking-wider">Pages</th>
                                      <th className="px-6 py-3 text-center text-xs font-medium text-text-secondary uppercase tracking-wider">Pages</th>
                                      <th className="px-4 py-3 text-center text-xs font-medium text-text-secondary uppercase tracking-wider w-12"></th>
                                    </tr>
                                  </thead>
                                  <tbody className="bg-white divide-y divide-border">
                                    {currentBookTopics.map(topic => (
                                      <tr 
                                        key={topic.id} 
                                        className={clsx(
                                          "group hover:bg-gray-50 transition cursor-pointer", 
                                          topic.completed && "opacity-60",
                                          selectedTopicForViewer?.id === topic.id && "bg-accent/5 ring-1 ring-inset ring-accent/20"
                                        )}
                                        onClick={() => setSelectedTopicForViewer({
                                          id: topic.id,
                                          document_id: topic.document_id,
                                          page_from: topic.page_start,
                                          page_to: topic.page_end,
                                          pdf_page_offset: topic.pdf_page_offset || 0,
                                          subject_name: subject.name,
                                          topic_title: topic.title
                                        })}
                                      >
                                        <td className="px-4 py-4 text-center">
                                          <button
                                            onClick={(e) => { e.stopPropagation(); handleToggleComplete(subject.id, topic.id); }}
                                            className="focus:outline-none transition-transform active:scale-90"
                                          >
                                            {topic.completed ? (
                                              <CheckCircle2 className="w-6 h-6 text-accent fill-accent/20" />
                                            ) : (
                                              <Circle className="w-6 h-6 text-gray-300 hover:text-accent/50" />
                                            )}
                                          </button>
                                        </td>
                                        <td className="px-6 py-4">
                                          <div className={clsx("text-sm font-medium", topic.completed ? "text-text-secondary line-through" : "text-text-primary")}>{topic.title}</div>
                                        </td>
                                        <td className="px-6 py-4 text-center whitespace-nowrap">
                                          <span className={clsx("text-sm font-medium px-2 py-1 rounded inline-block min-w-16", topic.completed ? "bg-gray-100 text-gray-400" : "bg-accent-light text-accent")}>
                                            {topic.page_start} - {topic.page_end}
                                          </span>
                                        </td>
                                        <td className="px-6 py-4 text-center whitespace-nowrap">
                                          <div className="text-sm font-bold text-text-primary bg-gray-50 px-3 py-1 rounded-md border border-border inline-block min-w-[3rem]">
                                            {topic.page_end - topic.page_start + 1}
                                          </div>
                                        </td>
                                        <td className="px-4 py-4 text-center">
                                          <button
                                            onClick={(e) => handleDeleteTopic(e, subject.id, topic.id, topic.title)}
                                            className="p-1.5 text-text-secondary hover:text-red-500 hover:bg-red-50 rounded-md transition opacity-0 group-hover:opacity-100"
                                            title="Delete Topic"
                                          >
                                            <Trash2 className="w-4 h-4" />
                                          </button>
                                          <button
                                            onClick={(e) => { e.stopPropagation(); handleCompletePrevious(subject.id, topic.id); }}
                                            className="p-1.5 text-text-secondary hover:text-accent hover:bg-accent/10 rounded-md transition opacity-0 group-hover:opacity-100"
                                            title="Mark all previous as done"
                                          >
                                            <CheckCircle2 className="w-4 h-4" />
                                          </button>
                                        </td>
                                      </tr>
                                    ))}
                                  </tbody>
                                </table>
                              </div>
                            </div>
                          </div>
                        </>
                      )}
                    </div>

                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
      </div>

      {/* Right side panel for PDF viewer - overlay on mobile, side panel on lg+ */}
      {selectedTopicForViewer && (
        <>
          {/* Mobile: full-screen overlay */}
          <div className="lg:hidden fixed inset-0 z-50 bg-surface">
            <PageViewer 
              slot={selectedTopicForViewer} 
              onClose={() => setSelectedTopicForViewer(null)} 
            />
          </div>
          {/* Desktop: side panel */}
          <div className="hidden lg:block lg:w-2/5 min-w-[380px] border-l border-border bg-surface h-full shadow-[-4px_0_15px_-3px_rgba(0,0,0,0.05)] z-10 flex-shrink-0">
            <PageViewer 
              slot={selectedTopicForViewer} 
              onClose={() => setSelectedTopicForViewer(null)} 
            />
          </div>
        </>
      )}

      {/* Subject Edit Modal */}
      {editingSubject && (
        <div className="fixed inset-0 bg-black/50 backdrop-blur-sm flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-3xl w-full max-w-md shadow-2xl overflow-hidden animate-in fade-in zoom-in duration-200">
            <div className="p-6 border-b border-border flex justify-between items-center bg-gray-50">
              <div>
                <h3 className="text-xl font-bold text-text-primary">Edit Subject</h3>
              </div>
              <button onClick={() => setEditingSubject(null)}><X className="w-6 h-6 text-text-secondary" /></button>
            </div>
            
            <div className="p-6 space-y-4 max-h-[60vh] overflow-y-auto">
              <div>
                <label className="block text-sm font-semibold text-text-secondary mb-1">Subject Name</label>
                <input 
                  className="w-full px-4 py-2 border border-border rounded-lg outline-none focus:ring-2 focus:ring-accent/20 focus:border-accent"
                  value={editingSubject.name}
                  onChange={e => setEditingSubject({...editingSubject, name: e.target.value})}
                />
              </div>
              
              <div>
                <label className="block text-sm font-semibold text-text-secondary mb-1">Weight</label>
                <input 
                  type="number"
                  step="0.1"
                  min="0.1"
                  className="w-full px-4 py-2 border border-border rounded-lg outline-none focus:ring-2 focus:ring-accent/20 focus:border-accent"
                  value={editingSubject.weight}
                  onChange={e => setEditingSubject({...editingSubject, weight: parseFloat(e.target.value)})}
                />
                <p className="text-xs text-text-secondary mt-1">Multiplier for frequency (e.g. 1.0 = normal, 2.0 = double paced)</p>
              </div>

              <div>
                <label className="block text-sm font-semibold text-text-secondary mb-2">Schedule Slot</label>
                <div className="flex bg-gray-100 p-1 rounded-xl">
                  {[
                    { id: 'A', name: 'Slot A' },
                    { id: 'B', name: 'Slot B' },
                    { id: 'C', name: 'Both (Daily)' }
                  ].map((slot) => (
                    <button
                      key={slot.id}
                      type="button"
                      onClick={() => setEditingSubject({...editingSubject, slot_type: slot.id})}
                      className={clsx(
                        "flex-1 py-2 rounded-lg text-sm font-bold transition whitespace-nowrap px-2",
                        editingSubject.slot_type === slot.id 
                          ? "bg-white text-accent shadow-sm" 
                          : "text-text-secondary hover:text-text-primary"
                      )}
                    >
                      {slot.name}
                    </button>
                  ))}
                </div>
                <p className="text-xs text-text-secondary mt-2">
                  {editingSubject.slot_type === 'A' 
                    ? "Slot A: Usually Mon/Wed/Fri sequence." 
                    : editingSubject.slot_type === 'B' 
                    ? "Slot B: Usually Tue/Thu sequence."
                    : "Both: Scheduled every single available study day."}
                </p>
              </div>

              <div>
                <label className="block text-sm font-semibold text-text-secondary mb-1">Target End Date (Optional)</label>
                <input 
                  type="date"
                  className="w-full px-4 py-2 border border-border rounded-lg outline-none focus:ring-2 focus:ring-accent/20 focus:border-accent"
                  value={editingSubject.end_date || ''}
                  onChange={e => setEditingSubject({...editingSubject, end_date: e.target.value})}
                />
                <p className="text-xs text-text-secondary mt-1">Leave blank to use the global calendar end date.</p>
              </div>

              {/* Books Offset Section */}
              <div className="pt-4 border-t border-border mt-6">
                <h4 className="text-sm font-bold text-text-primary mb-3">Book Offsets</h4>
                <p className="text-xs text-text-secondary mb-3">Adjust page numbering if the PDF doesn't match the table of contents.</p>
                
                {(() => {
                  const subjectTopics = topics[editingSubject.id] || [];
                  const booksMap = new Map();
                  subjectTopics.forEach(t => {
                    const fn = t.pdf_filename || 'Unknown Book';
                    if (!booksMap.has(fn) && fn !== 'Unknown Book') {
                      booksMap.set(fn, { filename: fn, offset: t.pdf_page_offset || 0 });
                    }
                  });
                  const booksList = Array.from(booksMap.values());
                  
                  if (booksList.length === 0) {
                     return <div className="text-xs text-gray-400 italic">No books uploaded yet.</div>;
                  }

                  return (
                    <div className="space-y-3">
                      {booksList.map((book) => (
                        <div key={book.filename} className="flex items-center justify-between border-b border-dashed border-border pb-2">
                          <span className="text-sm text-text-primary truncate mr-2 flex-1" title={book.filename}>
                            {book.filename}
                          </span>
                          <input 
                            type="number"
                            className="w-16 px-2 py-1 text-sm border border-border rounded-lg outline-none text-center focus:border-accent"
                            defaultValue={book.offset}
                            onBlur={(e) => {
                                const newOffset = parseInt(e.target.value, 10);
                                if (!isNaN(newOffset) && newOffset !== book.offset) {
                                  subjectsApi.setBookOffset(editingSubject.id, book.filename, newOffset)
                                    .then(() => loadTopics(editingSubject.id))
                                    .catch(err => console.error("Failed to set offset", err));
                                }
                            }}
                          />
                        </div>
                      ))}
                    </div>
                  );
                })()}
              </div>

              {/* Physical Book Support Section */}
              <div className="pt-4 border-t border-border mt-6">
                <div className="flex items-center justify-between mb-3">
                  <h4 className="text-sm font-bold text-text-primary">Physical Book Support</h4>
                  <span className="px-2 py-0.5 bg-accent/10 text-accent text-[10px] font-bold rounded-full uppercase">New</span>
                </div>
                <p className="text-xs text-text-secondary mb-4 leading-relaxed">
                  No PDF? No problem. Generate a list of generic chapters to organize your physical curriculum.
                </p>
                
                <div className="flex space-x-2 items-stretch">
                  <div className="flex-1 relative">
                    <input 
                      type="number"
                      min="1"
                      max="100"
                      className="w-full h-10 px-3 text-sm border border-border rounded-xl outline-none focus:border-accent focus:ring-2 focus:ring-accent/10 transition-all"
                      placeholder="Total Chapters"
                      value={chaptersCount}
                      onChange={(e) => setChaptersCount(parseInt(e.target.value) || 1)}
                    />
                    <div className="absolute right-3 top-1/2 -translate-y-1/2 text-[10px] font-bold text-text-secondary uppercase pointer-events-none">
                      Qty
                    </div>
                  </div>
                  <button
                    onClick={async () => {
                      if (window.confirm(`Action required: This will generate ${chaptersCount} generic chapters for this subject. Continue?`)) {
                        setGenerating(true);
                        try {
                          await subjectsApi.generateChapters(editingSubject.id, chaptersCount);
                          await loadTopics(editingSubject.id);
                        } catch {
                          alert("Failed to generate chapters.");
                        } finally {
                          setGenerating(false);
                        }
                      }
                    }}
                    disabled={generating}
                    className={clsx(
                      "h-10 px-4 rounded-xl text-sm font-bold transition-all flex items-center justify-center space-x-2 shadow-sm border border-border",
                      generating 
                        ? "bg-gray-50 text-text-secondary cursor-not-allowed" 
                        : "bg-surface hover:bg-gray-50 text-text-primary active:scale-95"
                    )}
                  >
                    {generating ? (
                      <>
                        <Loader2 className="w-4 h-4 animate-spin" />
                        <span>Generating...</span>
                      </>
                    ) : (
                      <>
                        <BookOpen className="w-4 h-4 text-accent" />
                        <span>Generate Chapters</span>
                      </>
                    )}
                  </button>
                </div>
              </div>

            </div>
            <div className="p-6 bg-gray-50 flex justify-end space-x-3 border-t border-border mt-auto">
              <button 
                onClick={() => setEditingSubject(null)}
                className="px-4 py-2 text-sm font-medium text-text-secondary hover:text-text-primary"
              >
                Cancel
              </button>
              <button 
                onClick={async () => {
                   try {
                     const payload = {
                         name: editingSubject.name,
                         weight: editingSubject.weight,
                         slot_type: editingSubject.slot_type,
                         end_date: editingSubject.end_date || null
                     };
                     await subjectsApi.update(editingSubject.id, payload);
                     loadSubjects();
                     setEditingSubject(null);
                   } catch { alert("Failed to save subject."); }
                }}
                className="bg-accent text-white px-6 py-2 rounded-xl font-bold hover:bg-accent-hover transition shadow-sm"
              >
                Save
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default Curriculum;
