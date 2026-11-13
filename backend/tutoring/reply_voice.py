"""A live reply is voiced the moment it is written, so the screen finds its voice ready.

The voice is the one the screen last played a reply in for this lesson; until it has
played one, nothing is voiced ahead. Every narration provider locks and reuses a
recording, so the screen's own request for the same reply waits and is never bought twice.
"""
import contextvars
import logging
import threading

logger = logging.getLogger(__name__)

_guard = threading.Lock()
_choices = {}   # session id -> how the screen asked for its last reply's voice
_started = set()


def remember(session_id, **choice):
    with _guard:
        _choices[session_id] = choice


def start(session_id, message_id):
    """Voice one saved reply in the background; returns the thread, or None."""
    with _guard:
        choice = _choices.get(session_id)
        if not choice or message_id in _started:
            return None
        if len(_started) > 5000:
            _started.clear()
        _started.add(message_id)
    thread = threading.Thread(target=contextvars.copy_context().run, args=(_speak, session_id, message_id, choice),
                              daemon=True, name="reply-voice")
    thread.start()
    return thread


def _speak(session_id, message_id, choice):
    from routers.tutor import speak_reply
    try:
        speak_reply(session_id, message_id, dry_run=False, **choice)
    except Exception as exc:  # the screen asks again and shows the words on their own if it fails
        logger.info("Reply %s was not voiced ahead: %s", message_id, getattr(exc, "detail", exc))
