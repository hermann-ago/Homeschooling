"""
AI Enrichment Service — Daily Canvas Phase 2
=============================================

Generates four types of AI-powered learning content for a given PDF section:
  - 'quiz'    : 5-question multiple-choice quiz
  - 'audio'   : Concise plain-text summary for browser TTS
  - 'terms'   : Key vocabulary as [{term, definition}] objects
  - 'explain' : "Explain Like I'm 10" plain-text paragraph

All functions:
  1. Accept extracted page text and a language hint ('pt' or 'en').
  2. Call gemini-2.5-flash (same model used by ai_analyzer.py).
  3. Are bilingual-aware — prompts adapt based on the language argument.
  4. Return Python objects (dicts / strings), NOT raw JSON strings.

PDF Extraction
--------------
`extract_pages_text()` reads specific physical pages from a stored PDF
using pdfplumber (already a project dependency). The caller must apply
the pdf_page_offset before calling this function.

Error Handling
--------------
All generation functions raise ValueError on Gemini API failure.
The router catches these and returns HTTP 502 with a user-friendly message.
"""

import os
import io
import json
import re
import pdfplumber
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()

# ── Gemini Configuration ──────────────────────────────────────────────────────

GEMINI_MODEL = "gemini-2.5-flash"

VALID_CONTENT_TYPES = {"quiz", "audio", "terms", "explain"}


def _get_model(response_json: bool = False) -> genai.GenerativeModel:
    """
    Instantiate a Gemini model, re-reading the API key at call time so
    that runtime key updates (via Settings page) are respected.
    """
    api_key = os.getenv("GEMINI_API_KEY", "")
    if not api_key or api_key == "your_key_here":
        raise ValueError(
            "Gemini API key not configured. "
            "Please add your API key in the Settings page."
        )
    genai.configure(api_key=api_key)

    config = {}
    if response_json:
        config["response_mime_type"] = "application/json"

    return genai.GenerativeModel(GEMINI_MODEL, generation_config=config)


# ── PDF Text Extraction ───────────────────────────────────────────────────────

def extract_pages_text(pdf_path: str, page_start: int, page_end: int, offset: int = 0) -> str:
    """
    Extract plain text from a physical page range in a PDF file.

    Args:
        pdf_path:   Relative path to the PDF (e.g. 'uploads/book.pdf').
        page_start: Logical (TOC) page number — start of the section.
        page_end:   Logical (TOC) page number — end of the section.
        offset:     pdf_page_offset stored on the topic (maps TOC→physical pages).

    Returns:
        Concatenated text of the requested pages.

    Raises:
        FileNotFoundError: If the PDF does not exist.
        ValueError: If the page range is invalid.
    """
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    # Convert logical page numbers to 0-based physical indices
    phys_start = max(0, (page_start + offset) - 1)
    phys_end = (page_end + offset) - 1  # inclusive

    text_parts = []
    with pdfplumber.open(pdf_path) as pdf:
        total = len(pdf.pages)
        phys_end = min(phys_end, total - 1)

        if phys_start > phys_end:
            raise ValueError(
                f"Invalid page range: physical [{phys_start+1}, {phys_end+1}] "
                f"(logical {page_start}–{page_end}, offset {offset})"
            )

        for page in pdf.pages[phys_start : phys_end + 1]:
            page_text = page.extract_text()
            if page_text:
                text_parts.append(page_text)

    return "\n\n".join(text_parts)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _language_label(language: str) -> str:
    """Convert language code to a display name for prompts."""
    return "Portuguese" if language == "pt" else "English"


def _clean_json(raw: str) -> str:
    """Strip markdown fences from Gemini's JSON response."""
    cleaned = raw.strip()
    cleaned = re.sub(r"^(?:```|''')(?:json)?\s*", "", cleaned)
    cleaned = re.sub(r"\s*(?:```|''')$", "", cleaned)
    return cleaned.strip()


# ── Generation Functions ──────────────────────────────────────────────────────

def generate_quiz(text: str, language: str = "en") -> list[dict]:
    """
    Generate a 5-question multiple-choice quiz from the provided text.

    Returns:
        List of 5 question dicts:
        [
          {
            "question": "...",
            "choices": ["A. ...", "B. ...", "C. ...", "D. ..."],
            "answer": "A"   # The letter of the correct choice
          },
          ...
        ]
    """
    lang = _language_label(language)
    prompt = f"""You are a friendly educational assistant creating a quiz for a grade-school student.
The content is in {lang}. Your response must ALSO be in {lang}.

Based on the text below, create a 5-question multiple-choice quiz.
Each question must have exactly 4 choices labeled A, B, C, D.
Indicate the correct answer letter.

Return ONLY a valid JSON array with this exact structure:
[
  {{
    "question": "...",
    "choices": ["A. ...", "B. ...", "C. ...", "D. ..."],
    "answer": "A"
  }}
]

TEXT:
---
{text[:4000]}
---"""

    model = _get_model(response_json=True)
    try:
        response = model.generate_content(prompt)
        parsed = json.loads(_clean_json(response.text))
        if not isinstance(parsed, list):
            raise ValueError("Expected a JSON array")
        return parsed[:5]  # Trim to 5 in case model returns more
    except Exception as e:
        raise ValueError(f"Quiz generation failed: {e}")


def generate_audio_summary(text: str, language: str = "en") -> str:
    """
    Generate a concise plain-text summary suitable for browser TTS.

    Returns:
        A 3–5 sentence plain-text summary string. No markdown, no lists —
        just flowing sentences the SpeechSynthesis API can read naturally.
    """
    lang = _language_label(language)
    prompt = f"""You are a friendly educational assistant writing a study summary for a grade-school student.
The content is in {lang}. Your response must ALSO be in {lang}.

Write a clear, simple, 3 to 5 sentence summary of the key points in the text below.
Rules:
- Write in plain sentences only (no bullet points, no markdown, no headers).
- Use simple vocabulary suitable for a child aged 8–14.
- The summary will be read aloud by a text-to-speech system.

TEXT:
---
{text[:4000]}
---

Return ONLY the summary text."""

    model = _get_model(response_json=False)
    try:
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        raise ValueError(f"Audio summary generation failed: {e}")


def generate_key_terms(text: str, language: str = "en") -> list[dict]:
    """
    Extract 5–8 key vocabulary terms with definitions from the provided text.

    Returns:
        List of term dicts:
        [{"term": "...", "definition": "..."}, ...]
    """
    lang = _language_label(language)
    prompt = f"""You are a friendly educational assistant helping a grade-school student learn vocabulary.
The content is in {lang}. Your response must ALSO be in {lang}.

From the text below, extract between 5 and 8 important key terms or concepts.
For each term, write a simple, one-sentence definition a child aged 8–14 can understand.

Return ONLY a valid JSON array with this exact structure:
[
  {{"term": "...", "definition": "..."}}
]

TEXT:
---
{text[:4000]}
---"""

    model = _get_model(response_json=True)
    try:
        response = model.generate_content(prompt)
        parsed = json.loads(_clean_json(response.text))
        if not isinstance(parsed, list):
            raise ValueError("Expected a JSON array")
        return parsed[:8]
    except Exception as e:
        raise ValueError(f"Key terms generation failed: {e}")


def generate_explain_simple(text: str, language: str = "en") -> str:
    """
    Rewrite the content as a simple, friendly explanation for a grade-school child.

    Returns:
        A plain-text paragraph (3–6 sentences) using simple language.
    """
    lang = _language_label(language)
    prompt = f"""You are a friendly educational assistant explaining a topic to a grade-school student.
The content is in {lang}. Your response must ALSO be in {lang}.

Rewrite the main ideas from the text below as if you are explaining them to a curious 10-year-old child.
Rules:
- Use simple, everyday words.
- Keep it to 3 to 6 sentences.
- Make it friendly, warm, and encouraging.
- No bullet points, no markdown — just plain flowing sentences.

TEXT:
---
{text[:4000]}
---

Return ONLY the explanation text."""

    model = _get_model(response_json=False)
    try:
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        raise ValueError(f"Simple explanation generation failed: {e}")


# ── Dispatcher ────────────────────────────────────────────────────────────────

def generate_content(content_type: str, text: str, language: str = "en"):
    """
    Dispatch to the appropriate generation function based on content_type.

    Args:
        content_type: One of 'quiz', 'audio', 'terms', 'explain'.
        text:         Extracted PDF page text.
        language:     'pt' or 'en'.

    Returns:
        The raw Python object (list or str) returned by the generator.

    Raises:
        ValueError: For unknown content_type or Gemini failures.
    """
    if content_type not in VALID_CONTENT_TYPES:
        raise ValueError(
            f"Unknown content_type '{content_type}'. "
            f"Must be one of: {VALID_CONTENT_TYPES}"
        )

    generators = {
        "quiz": generate_quiz,
        "audio": generate_audio_summary,
        "terms": generate_key_terms,
        "explain": generate_explain_simple,
    }
    return generators[content_type](text, language)
