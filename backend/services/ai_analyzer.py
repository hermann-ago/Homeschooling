"""
AI curriculum analyzer using Google Gemini API.
Handles bilingual content (Portuguese/English).
"""
import os
import json
import re
import warnings

# Suppress the deprecation warning for google-generativeai
with warnings.catch_warnings():
    warnings.filterwarnings("ignore", category=FutureWarning, module="google.generativeai")
    import google.generativeai as genai

from dotenv import load_dotenv

load_dotenv()

# Configure Gemini
api_key = os.getenv("GEMINI_API_KEY", "")
if api_key and api_key != "your_key_here":
    genai.configure(api_key=api_key)

SYSTEM_INSTRUCTION = """You are an expert curriculum analyst for homeschool education.
You analyze the Table of Contents (TOC) or index from textbooks and extract structured chapter/topic information.

CRITICAL RULES:
1. Detect the language of the content (Portuguese or English) and respond in the SAME language for topic titles.
2. Return ONLY valid JSON.
3. Follow the exact JSON schema provided below.
4. If a topic has no explicit page range in the TOC, estimate it based on the surrounding topics or total page count.

Expected JSON schema:
{
  "language": "pt" or "en",
  "topics": [
    {
      "title": "Chapter/topic title in the original language",
      "page_start": <integer>,
      "page_end": <integer>
    }
  ]
}
"""


def analyze_curriculum(text: str, page_count: int) -> dict:
    """
    Send extracted PDF text (TOC) to Gemini for curriculum analysis.
    """
    current_key = os.getenv("GEMINI_API_KEY", "")
    if not current_key or current_key == "your_key_here":
        raise ValueError(
            "Gemini API key not configured. "
            "Please add your API key to the .env file: GEMINI_API_KEY=your_actual_key"
        )

    # Re-configure in case key was updated at runtime
    genai.configure(api_key=current_key)

    model = genai.GenerativeModel(
        "gemini-2.5-flash",
        system_instruction=SYSTEM_INSTRUCTION,
        generation_config={"response_mime_type": "application/json"}
    )

    # Build the user prompt focused on TOC
    user_prompt = f"""The following text is the Table of Contents or index from a textbook.
The total number of pages in the full book is: {page_count}.

Please extract the chapters/topics as a structured curriculum. 
Ensure the combined topics cover the full book (up to page {page_count}).

TOC Content:
---
{text}
---

Return ONLY the JSON object."""

    try:
        response = model.generate_content(user_prompt)
        return _parse_response(response.text, page_count)
    except Exception as e:
        raise ValueError(f"Gemini API call failed: {str(e)}")


def _parse_response(response_text: str, page_count: int) -> dict:
    """
    Parse Gemini's response, extracting JSON even if surrounded by text/markdown.
    """
    # 1. Clean up potential markdown fences/triple quotes from the raw response
    cleaned = response_text.strip()
    cleaned = re.sub(r"^(?:```|''')(?:json)?\s*", "", cleaned)
    cleaned = re.sub(r"\s*(?:```|''')$", "", cleaned)
    cleaned = cleaned.strip()

    # 2. Try direct parsing
    result = None
    try:
        result = json.loads(cleaned)
    except json.JSONDecodeError:
        # 3. Try to wrap in braces if it looks like partial content (missing outer braces)
        if '"topics"' in cleaned and not cleaned.startswith("{"):
            try:
                result = json.loads("{" + cleaned + "}")
            except json.JSONDecodeError:
                pass
        
        # 4. Try to extract the first JSON object using regex (might be surrounded by text)
        if result is None:
            match = re.search(r"\{.*\}", cleaned, re.DOTALL)
            if match:
                try:
                    result = json.loads(match.group(0))
                except json.JSONDecodeError:
                    pass

    if result is None:
        raise ValueError(f"Failed to parse Gemini response as JSON.\nResponse snippet: {response_text[:500]}")

    # Validate structure
    if "topics" not in result or not isinstance(result["topics"], list):
        # If it's just a list of topics, wrap it
        if isinstance(result, list):
            result = {"topics": result}
        else:
            raise ValueError("Gemini response missing 'topics' list")

    # Sanitize page ranges
    for topic in result["topics"]:
        topic["page_start"] = max(1, int(topic.get("page_start", 1)))
        topic["page_end"] = min(page_count, int(topic.get("page_end", page_count)))
        # No longer requesting complexity, but ensuring it has a default for the DB
        if "complexity" not in topic:
            topic["complexity"] = 1

    return result
