import { fetchApi } from './client';

export const canvasApi = {
  // ── Phase 1: Canvas Slots & Inserts ────────────────────────────────────────
  getToday: (childId) => fetchApi(`/canvas/${childId}/today`),

  createInsert: (data) => fetchApi('/canvas/insert', {
    method: 'POST',
    body: JSON.stringify(data),
  }),

  deleteInsert: (insertId) => fetchApi(`/canvas/insert/${insertId}`, {
    method: 'DELETE',
  }),

  getAvailableTopics: (childId) => fetchApi(`/canvas/${childId}/available-topics`),

  // ── Phase 2: AI Enrichment ─────────────────────────────────────────────────

  /**
   * Generate (or fetch from cache) AI content for a canvas section.
   * @param {Object} data - { topic_id, page_start, page_end, content_type, source_text, language }
   * @returns {Promise<Object>} CanvasAIResponse with `content` and `from_cache` fields.
   */
  generateAIContent: (data) => fetchApi('/canvas/ai-content/generate', {
    method: 'POST',
    body: JSON.stringify(data),
  }),

  /**
   * Return all cached AI enrichment rows for a topic (used to show ⚡ badges).
   * @param {number} topicId
   * @returns {Promise<Array>} Array of CanvasAIResponse objects.
   */
  getAIContentForTopic: (topicId) => fetchApi(`/canvas/ai-content/${topicId}`),
};

