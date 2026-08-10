import { useCallback, useEffect, useReducer, useRef, useState } from 'react';
import {
  AnnotationConflictError,
  getPageAnnotations,
  savePageAnnotations,
} from '../../api/annotations';
import {
  annotationHistoryReducer,
  createAnnotationHistory,
} from './annotationGeometry';


function draftKey(childId, documentId, pageNumber) {
  return `homeschool:pdf-annotations:v1:${childId}:${documentId}:${pageNumber}`;
}


function readDraft(key) {
  try {
    const value = JSON.parse(localStorage.getItem(key));
    if (value && Array.isArray(value.strokes) && Number.isInteger(value.baseRevision)) {
      return value;
    }
  } catch {
    // Ignore malformed or unavailable local storage.
  }
  return null;
}


function writeDraft(key, strokes, baseRevision) {
  try {
    localStorage.setItem(key, JSON.stringify({ strokes, baseRevision, savedAt: Date.now() }));
  } catch {
    // The in-memory drawing remains available even if local storage is full.
  }
}


function removeDraft(key) {
  try {
    localStorage.removeItem(key);
  } catch {
    // Ignore unavailable local storage.
  }
}


export function usePageAnnotations({ childId, documentId, pageNumber, enabled }) {
  const [history, dispatch] = useReducer(annotationHistoryReducer, createAnnotationHistory());
  const [revision, setRevision] = useState(0);
  const [saveStatus, setSaveStatus] = useState(enabled ? 'loading' : 'saved');
  const [error, setError] = useState('');
  const [conflict, setConflict] = useState(null);
  const [dirty, setDirty] = useState(false);

  const strokesRef = useRef(history.present);
  const revisionRef = useRef(revision);
  const dirtyRef = useRef(dirty);
  const conflictRef = useRef(conflict);
  const changeVersionRef = useRef(0);
  const savingRef = useRef(null);
  const key = draftKey(childId, documentId, pageNumber);

  useEffect(() => { strokesRef.current = history.present; }, [history.present]);
  useEffect(() => { revisionRef.current = revision; }, [revision]);
  useEffect(() => { dirtyRef.current = dirty; }, [dirty]);
  useEffect(() => { conflictRef.current = conflict; }, [conflict]);

  useEffect(() => {
    if (!enabled) {
      dispatch({ type: 'load', strokes: [] });
      setRevision(0);
      setSaveStatus('saved');
      setDirty(false);
      setConflict(null);
      return undefined;
    }

    let active = true;
    setSaveStatus('loading');
    setError('');
    setConflict(null);
    setDirty(false);
    dirtyRef.current = false;
    savingRef.current = null;
    changeVersionRef.current += 1;

    getPageAnnotations(childId, documentId, pageNumber)
      .then((serverPage) => {
        if (!active) return;
        const draft = readDraft(key);
        setRevision(serverPage.revision);
        revisionRef.current = serverPage.revision;
        if (draft) {
          dispatch({ type: 'load', strokes: draft.strokes });
          strokesRef.current = draft.strokes;
          if (draft.baseRevision === serverPage.revision) {
            setDirty(true);
            dirtyRef.current = true;
            setSaveStatus('unsaved');
          } else {
            setConflict(serverPage);
            conflictRef.current = serverPage;
            setDirty(true);
            dirtyRef.current = true;
            setSaveStatus('conflict');
          }
        } else {
          dispatch({ type: 'load', strokes: serverPage.strokes });
          strokesRef.current = serverPage.strokes;
          setSaveStatus('saved');
        }
      })
      .catch((nextError) => {
        if (!active) return;
        const draft = readDraft(key);
        if (draft) {
          dispatch({ type: 'load', strokes: draft.strokes });
          strokesRef.current = draft.strokes;
          setRevision(draft.baseRevision);
          revisionRef.current = draft.baseRevision;
          setDirty(true);
          dirtyRef.current = true;
        }
        setError(nextError.message);
        setSaveStatus('error');
      });

    return () => { active = false; };
  }, [childId, documentId, enabled, key, pageNumber]);

  const saveNow = useCallback(async () => {
    if (!enabled || !dirtyRef.current || conflictRef.current) return true;
    if (savingRef.current) {
      await savingRef.current;
      return !dirtyRef.current;
    }

    const capturedStrokes = strokesRef.current;
    const capturedRevision = revisionRef.current;
    const capturedVersion = changeVersionRef.current;
    setSaveStatus('saving');
    setError('');

    const operation = savePageAnnotations(
      childId,
      documentId,
      pageNumber,
      capturedRevision,
      capturedStrokes,
    ).then((savedPage) => {
      setRevision(savedPage.revision);
      revisionRef.current = savedPage.revision;
      if (changeVersionRef.current === capturedVersion) {
        setDirty(false);
        dirtyRef.current = false;
        setSaveStatus('saved');
        removeDraft(key);
      } else {
        writeDraft(key, strokesRef.current, savedPage.revision);
        setSaveStatus('unsaved');
      }
      return true;
    }).catch((nextError) => {
      if (nextError instanceof AnnotationConflictError) {
        setConflict(nextError.current);
        conflictRef.current = nextError.current;
        setSaveStatus('conflict');
      } else {
        setError(nextError.message);
        setSaveStatus('error');
      }
      writeDraft(key, strokesRef.current, revisionRef.current);
      return false;
    }).finally(() => {
      savingRef.current = null;
    });

    savingRef.current = operation;
    return operation;
  }, [childId, documentId, enabled, key, pageNumber]);

  useEffect(() => {
    if (!dirty || conflict || saveStatus === 'loading') return undefined;
    const timeout = window.setTimeout(saveNow, 600);
    return () => window.clearTimeout(timeout);
  }, [conflict, dirty, history.present, saveNow, saveStatus]);

  useEffect(() => {
    if (!enabled) return undefined;
    const handleOnline = () => saveNow();
    const handleVisibility = () => {
      if (document.visibilityState === 'hidden') saveNow();
    };
    window.addEventListener('online', handleOnline);
    document.addEventListener('visibilitychange', handleVisibility);
    return () => {
      window.removeEventListener('online', handleOnline);
      document.removeEventListener('visibilitychange', handleVisibility);
    };
  }, [enabled, saveNow]);

  const recordChange = useCallback((nextStrokes) => {
    dispatch({ type: 'commit', strokes: nextStrokes });
    strokesRef.current = nextStrokes;
    changeVersionRef.current += 1;
    setDirty(true);
    dirtyRef.current = true;
    setSaveStatus('unsaved');
    setError('');
    writeDraft(key, nextStrokes, revisionRef.current);
  }, [key]);

  const addStroke = useCallback((stroke) => {
    recordChange([...strokesRef.current, stroke]);
  }, [recordChange]);

  const eraseStrokes = useCallback((strokeIds) => {
    const ids = new Set(strokeIds);
    const next = strokesRef.current.filter((stroke) => !ids.has(stroke.id));
    if (next.length !== strokesRef.current.length) recordChange(next);
  }, [recordChange]);

  const clear = useCallback(() => {
    if (strokesRef.current.length) recordChange([]);
  }, [recordChange]);

  const undo = useCallback(() => {
    if (!history.past.length) return;
    const next = history.past[history.past.length - 1];
    dispatch({ type: 'undo' });
    strokesRef.current = next;
    changeVersionRef.current += 1;
    setDirty(true);
    dirtyRef.current = true;
    setSaveStatus('unsaved');
    writeDraft(key, next, revisionRef.current);
  }, [history.past, key]);

  const redo = useCallback(() => {
    if (!history.future.length) return;
    const next = history.future[0];
    dispatch({ type: 'redo' });
    strokesRef.current = next;
    changeVersionRef.current += 1;
    setDirty(true);
    dirtyRef.current = true;
    setSaveStatus('unsaved');
    writeDraft(key, next, revisionRef.current);
  }, [history.future, key]);

  const reloadConflict = useCallback(() => {
    if (!conflictRef.current) return;
    const serverPage = conflictRef.current;
    dispatch({ type: 'load', strokes: serverPage.strokes });
    strokesRef.current = serverPage.strokes;
    setRevision(serverPage.revision);
    revisionRef.current = serverPage.revision;
    setConflict(null);
    conflictRef.current = null;
    setDirty(false);
    dirtyRef.current = false;
    setSaveStatus('saved');
    removeDraft(key);
  }, [key]);

  const keepMine = useCallback(() => {
    if (!conflictRef.current) return;
    const nextRevision = conflictRef.current.revision;
    setRevision(nextRevision);
    revisionRef.current = nextRevision;
    setConflict(null);
    conflictRef.current = null;
    setDirty(true);
    dirtyRef.current = true;
    setSaveStatus('unsaved');
    writeDraft(key, strokesRef.current, nextRevision);
    window.setTimeout(saveNow, 0);
  }, [key, saveNow]);

  return {
    strokes: history.present,
    loading: saveStatus === 'loading',
    saveStatus,
    error,
    conflict,
    canUndo: history.past.length > 0,
    canRedo: history.future.length > 0,
    addStroke,
    eraseStrokes,
    clear,
    undo,
    redo,
    retry: saveNow,
    flush: saveNow,
    reloadConflict,
    keepMine,
  };
}
