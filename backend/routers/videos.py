"""A book's video lessons: the subject's video pages, and one lesson's video."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from dependencies import require_family, store
from tutoring import videos
from tutoring.service import TutorError
from utils import get_or_404

router = APIRouter()


class VideoPages(BaseModel):
    pages: list[str] = Field(default_factory=list, max_length=20)


class LessonVideo(BaseModel):
    url: str | None = Field(None, max_length=500)
    hidden: bool = False


def _lesson_videos(db, subject_id):
    topics = sorted((t for t in db.find('topics', subject_id=subject_id) if not t.get('archived')),
                    key=lambda t: (t.get('chapter_order') or 0, t['id']))
    return [{'topic_id': t['id'], 'title': t['title'], 'video': videos.for_topic(db, t['id']),
             'hidden': any(r['source'] == 'hidden' for r in db.find('topic_videos', topic_id=t['id']))} for t in topics]


@router.get('/subjects/{subject_id}/videos', dependencies=[Depends(require_family)])
def subject_videos(subject_id: int):
    db = store()
    subject = get_or_404(db, 'subjects', subject_id)
    return {'pages': subject.get('video_pages') or [], 'lessons': _lesson_videos(db, subject_id)}


@router.post('/subjects/{subject_id}/videos/find', dependencies=[Depends(require_family)])
def find_videos(subject_id: int, payload: VideoPages):
    db = store()
    get_or_404(db, 'subjects', subject_id)
    try:
        found = videos.find(db, subject_id, payload.pages)
    except TutorError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {**found, 'lessons': _lesson_videos(db, subject_id)}


@router.put('/topics/{topic_id}/video', dependencies=[Depends(require_family)])
def set_lesson_video(topic_id: int, payload: LessonVideo):
    try:
        return {'video': videos.set_for_topic(store(), topic_id, payload.url, payload.hidden)}
    except TutorError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.delete('/topics/{topic_id}/video', status_code=204, dependencies=[Depends(require_family)])
def clear_lesson_video(topic_id: int):
    get_or_404(store(), 'topics', topic_id)
    videos.clear_for_topic(store(), topic_id)
