"""Guided lessons: the book passage walked through by a teacher's voice.

An AI writes a *plan* for the lesson: a short introduction, the book text in
order, a few short explanations between parts of it, and a recap. The plan
never carries the book text itself in the usual ("expand") mode; it names
ranges of the passage's sentences, and the server puts the book's own words
in. Whatever the AI returns, every sentence of the passage is read, once and
in order, so a guided lesson can add to the book but never drop or change it.

Some lessons already are a teacher's script (Say:, Ask:, notes to the parent,
exercise instructions). For those the AI may choose "tidy": it rewrites the
reading parts into one clean, concise spoken walk-through. Each rewritten part
still names the sentences it covers, so the original page can follow along.

The guide is saved as JSON in the subject's Lesson Content folder and indexed
in the ``guides`` table with the passage it was written for; when the book
text or boundaries change, the old guide is shown as out of date. Its voice
is an ordinary narration track built from the guide's sentences.
"""
from __future__ import annotations

import json
import os
import re
import uuid
from datetime import datetime, timezone

from storage import layout

from .passages import passage_sha256, split_sentences

GUIDE_VERSION = 1
# Tried on real lessons (Sep 2026): Pro writes the clearest teaching for young learners; Flash is the
# fast fallback. "latest" names follow Google's current models instead of breaking when one retires.
DEFAULT_MODELS = ("gemini-pro-latest", "gemini-flash-latest")
TEACHER_TYPES = ("intro", "explain", "recap")
MAX_TEACHER_CHARACTERS = 700


class GuideError(ValueError):
    pass


# ── The AI's plan ────────────────────────────────────────────────────────────

LANGUAGES = {"en-US": "English", "pt-BR": "Brazilian Portuguese"}


def prompt(passage: dict, *, subject: str, learner: str, grade: str | None, language: str) -> str:
    numbered = "\n".join(f"[{i}] {s['text']}" for i, s in enumerate(passage["sentences"]))
    audience = f"{learner}, a homeschooled child" + (f" in {grade} grade" if grade and grade != "N/A" else "")
    return f"""You are a warm, clear homeschool teacher preparing a lesson that will be read aloud by a
text-to-speech voice to {audience}. Everything you write is spoken, in {LANGUAGES.get(language, "English")}.

Lesson: "{passage["title"]}" ({subject}).
The lesson's text from the book, one numbered sentence per line:
{numbered}

Plan the spoken lesson as a list of segments, in order:
- "intro": 2 to 4 sentences that welcome {learner} by name, say what the lesson is about and why it is interesting,
  and connect it to something a child knows.
- "read": the book text. Give the range of sentence numbers with "from" and "to" (inclusive).
- "explain": 1 to 3 short spoken sentences between reading parts, like a teacher pausing. Each one must ADD
  something the book does not say plainly: what a hard word means, why something matters, how it connects to what a
  child knows or to earlier events, what to picture, or what to listen for in the next part ("Listen for…"). Or ask
  one question to think about. Never just retell what was just read. Don't answer questions the child is meant to
  answer in exercises.
- "recap": 2 to 4 sentences at the end that pull out the two or three big ideas, not a retelling of every event.

Choose the mode:
- "expand" (usual): the text is ordinary reading. Read segments must cover every sentence exactly once, in order,
  from 0 to {len(passage["sentences"]) - 1}. Pause after a paragraph or every 4 to 8 sentences, only where a pause
  helps; all teacher parts together should be about a third as long as the reading. Do not rewrite the book text.
- "tidy": the text is already a teacher's script or lesson plan (for example "Say:", "Ask the child", notes to the
  parent, exercise instructions, answer blanks). Then give each "read" segment a "text" that turns those parts into
  clean, concise spoken teaching addressed to the child, keeping all of the lesson's content and dropping notes meant
  only for the parent, page numbers and repeated headings. Still give "from" and "to" for the sentences it covers.

Rules: plain spoken sentences only (no markdown, lists, emoji or stage directions); short sentences suit a
{grade or "young"} learner; a calm, friendly voice, not an excited one (no "Wow", at most one exclamation mark in
the whole lesson); never invent facts that are not in the text or common knowledge; keep teacher parts brief.

Reply with JSON only:
{{"mode": "expand" or "tidy", "segments": [{{"type": "intro", "text": "..."}}, {{"type": "read", "from": 0, "to": 3}},
{{"type": "explain", "text": "..."}}, ..., {{"type": "recap", "text": "..."}}]}}"""


def gemini_writer(prompt_text: str, model: str) -> dict:
    """Ask Gemini for the plan (JSON). Raises GuideError when it cannot."""
    api_key = os.getenv("GEMINI_API_KEY", "")
    if not api_key or api_key == "your_key_here":
        raise GuideError("The AI key is not set on the home server (GEMINI_API_KEY in backend/.env)")
    from google import genai
    from google.genai import types
    client = genai.Client(api_key=api_key)
    try:
        response = client.models.generate_content(
            model=model, contents=prompt_text,
            config=types.GenerateContentConfig(response_mime_type="application/json", temperature=0.5))
        return json.loads(response.text)
    except json.JSONDecodeError as error:
        raise GuideError("The AI's answer was not valid JSON; try again") from error
    except Exception as error:  # network, quota or model errors
        raise GuideError(f"The AI could not write the guide: {error}") from error


# ── Turning the plan into the spoken guide ───────────────────────────────────

def _spoken(text) -> str:
    text = re.sub(r"[*_#`>]+", "", str(text or ""))
    text = re.sub(r"\s+", " ", text).strip()
    return text[:MAX_TEACHER_CHARACTERS]


def _index(value, default: int | None) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def build(passage_sentences: list[dict], plan: dict) -> dict:
    """The guide's segments and sentences from the AI's plan (see the module docstring)."""
    count = len(passage_sentences)
    if not count:
        raise GuideError("This lesson has no text to guide")
    raw = plan.get("segments") if isinstance(plan, dict) else None
    if not isinstance(raw, list):
        raise GuideError("The AI's plan had no segments; try again")
    mode = plan.get("mode") if plan.get("mode") in ("expand", "tidy") else "expand"
    verbatim = lambda first, last: " ".join(s["text"] for s in passage_sentences[first:last + 1])  # noqa: E731

    segments, cursor = [], 0
    for item in raw:
        if not isinstance(item, dict):
            continue
        kind = item.get("type")
        if kind in TEACHER_TYPES:
            text = _spoken(item.get("text"))
            if text:
                segments.append({"type": kind, "text": text})
        elif kind == "read" and mode == "expand":
            if cursor >= count:
                continue
            last = min(max(_index(item.get("to"), cursor), cursor), count - 1)
            segments.append({"type": "read", "from": cursor, "to": last})  # starts where the last one ended
            cursor = last + 1
        elif kind == "read":
            first, last = _index(item.get("from"), None), _index(item.get("to"), None)
            valid = first is not None and last is not None and 0 <= first <= last < count
            text = _spoken(item.get("text")) or (verbatim(first, last) if valid else "")
            if text:
                segments.append({"type": "read", "text": text, "from": first if valid else None,
                                 "to": last if valid else None})
    if mode == "expand" and cursor < count:
        # Anything the plan skipped is read after its last reading part, so no book text is lost.
        after_last_read = max((i + 1 for i, s in enumerate(segments) if s["type"] == "read"), default=len(segments))
        segments.insert(after_last_read, {"type": "read", "from": cursor, "to": count - 1})
    if not any(s["type"] == "read" for s in segments):
        segments.append({"type": "read", "from": 0, "to": count - 1})

    sentences = []
    for segment in segments:
        if segment["type"] != "read":
            sentences += [{"text": s["text"], "kind": "teacher", "source": None} for s in split_sentences(segment["text"])]
        elif "text" not in segment:
            sentences += [{"text": passage_sentences[i]["text"], "kind": "book", "source": i}
                          for i in range(segment["from"], segment["to"] + 1)]
        else:
            parts = split_sentences(segment["text"])
            first, last = segment["from"], segment["to"]
            for k, part in enumerate(parts):
                source = None if first is None else first + (k * (last - first + 1)) // len(parts)
                sentences.append({"text": part["text"], "kind": "book", "source": source})
    for index, sentence in enumerate(sentences):
        sentence["paragraphIndex"] = index  # each sentence is spoken on its own
    return {"mode": mode, "segments": segments, "sentences": sentences}


def guide_sha(sentences: list[dict]) -> str:
    return passage_sha256(json.dumps([s["text"] for s in sentences], ensure_ascii=False))


# ── Storage ──────────────────────────────────────────────────────────────────

def current_row(store, topic_id: int, source_sha: str) -> tuple[dict | None, bool]:
    """(latest guide row, whether it was written for this passage text)."""
    rows = sorted(store.find("guides", topic_id=topic_id), key=lambda r: r["created_at"], reverse=True)
    if not rows:
        return None, False
    return rows[0], rows[0]["source_sha256"] == source_sha


def package(ctx, row: dict, fresh: bool) -> dict:
    """The guide as the reader and narration use it (a passage-like object)."""
    content = json.loads(ctx.file_bytes(row["guide_path"], None))
    return {"guide_id": row["id"], "mode": row["mode"], "model": row["model"], "language": row["language"],
            "created_at": row["created_at"].isoformat() if row["created_at"] else None,
            "current": fresh, "sentences": content["sentences"], "passage_sha256": row["guide_sha256"],
            "title": content.get("title")}


def save(tx, topic: dict, passage: dict, guide: dict, *, model: str, language: str) -> dict:
    sha = guide_sha(guide["sentences"])
    content = {"version": GUIDE_VERSION, "topic_id": topic["id"], "title": passage["title"],
               "source_passage_sha256": passage["passage_sha256"], "mode": guide["mode"], "model": model,
               "language": language, "created_at": datetime.now(timezone.utc).isoformat(),
               "segments": guide["segments"], "sentences": guide["sentences"]}
    folder = layout.for_topic(tx, topic["id"], layout.LESSON_CONTENT)
    path, file_sha = tx.add_blob(json.dumps(content, ensure_ascii=False, indent=1).encode("utf-8"), folder,
                                 f"guided-lesson-topic{topic['id']}-{sha[:12]}.json", "application/json")
    return tx.insert("guides", {
        "id": f"guide-{topic['id']}-{uuid.uuid4().hex[:10]}", "topic_id": topic["id"],
        "source_sha256": passage["passage_sha256"], "guide_sha256": sha, "guide_path": path, "guide_file_sha256": file_sha,
        "mode": guide["mode"], "model": model, "language": language,
        "sentence_count": len(guide["sentences"]),
        "character_count": sum(len(s["text"]) for s in guide["sentences"])})


def write_plan(prompt_text: str, models) -> tuple[dict, str]:
    """(plan, model that wrote it): the first model that answers. Kept in one place so tests can replace it."""
    failure = None
    for model in models:
        try:
            return gemini_writer(prompt_text, model), model
        except GuideError as error:
            failure = error
    raise failure or GuideError("No AI model is configured")
