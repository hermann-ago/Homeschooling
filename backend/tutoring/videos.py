"""Video lessons that a book points to, such as "watch the video lesson on …".

A grown-up gives a subject the publisher's video pages once. The pages are
read for embedded players; each video's own title ("Lesson 18 | …") is matched
to the lesson with the same number. Videos stay on the publisher's player:
nothing is downloaded or copied. A grown-up can set or hide one lesson's video.
"""
from __future__ import annotations

import ipaddress
import re
import socket
import time
from datetime import datetime, timezone
from urllib.parse import parse_qs, urlparse

import httpx

from .service import TutorError

VIMEO = re.compile(r'(?:player\.vimeo\.com/video/|vimeo\.com/)(\d{5,})(?:(?:\?h=|/)([0-9a-f]{6,}))?')
YOUTUBE = re.compile(r'(?:youtube(?:-nocookie)?\.com/(?:embed/|watch\?v=|shorts/)|youtu\.be/)([\w-]{11})')
EMBED = re.compile(r'<iframe[^>]+src="([^"]+)"', re.I)
NUMBER = re.compile(r'\d+')
AGENT = {'User-Agent': 'Homeschooling home app (video lesson links)'}


def _now():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


def parse(url):
    """A video link or player address → the player's identity, or None."""
    text = str(url or '').strip()
    if match := VIMEO.search(text):
        return {'provider': 'vimeo', 'video_id': match[1], 'key': match[2] or (parse_qs(urlparse(text).query).get('h') or [None])[0]}
    if match := YOUTUBE.search(text):
        return {'provider': 'youtube', 'video_id': match[1], 'key': None}
    return None


def player(video):
    """Where the video plays inside a lesson, and where it opens on its own."""
    vid, key = video['video_id'], video.get('key')
    if video['provider'] == 'vimeo':
        return {'embed_url': f"https://player.vimeo.com/video/{vid}?{'h=' + key + '&' if key else ''}dnt=1&title=0&byline=0&portrait=0",
                'open_url': f"https://vimeo.com/{vid}{'/' + key if key else ''}"}
    return {'embed_url': f'https://www.youtube-nocookie.com/embed/{vid}?rel=0', 'open_url': f'https://www.youtube.com/watch?v={vid}'}


def _public_https(url):
    parsed = urlparse(url)
    if parsed.scheme != 'https' or not parsed.hostname:
        raise TutorError('Use an https:// web address for the video page')
    try:
        addresses = {info[4][0] for info in socket.getaddrinfo(parsed.hostname, 443)}
    except OSError as exc:
        raise TutorError(f'The video page {parsed.hostname} could not be found') from exc
    if any(not ipaddress.ip_address(a.split('%')[0]).is_global for a in addresses):
        raise TutorError('Video pages must be on the public web, not this home network')


def _title(http, video):
    target = (f"https://vimeo.com/{video['video_id']}{'/' + video['key'] if video.get('key') else ''}" if video['provider'] == 'vimeo'
              else f"https://www.youtube.com/watch?v={video['video_id']}")
    endpoint = 'https://vimeo.com/api/oembed.json' if video['provider'] == 'vimeo' else 'https://www.youtube.com/oembed'
    try:
        reply = http.get(endpoint, params={'url': target, 'format': 'json'}, headers=AGENT, timeout=20)
        return reply.json().get('title') if reply.status_code == 200 else None
    except (httpx.HTTPError, ValueError):
        return None


def lesson_number(title):
    match = NUMBER.search(str(title or ''))
    return int(match[0]) if match else None


def public(row):
    if not row or row.get('source') == 'hidden':
        return None
    return {'title': row.get('title'), 'provider': row['provider'], 'source': row['source'], **player(row)}


def for_topic(db, topic_id):
    rows = db.find('topic_videos', topic_id=topic_id)
    return public(rows[0]) if rows else None


def find(db, subject_id, pages, http=None):
    """Read the pages, match each video to the lesson with its number."""
    pages = [p.strip() for p in pages if p and p.strip()]
    if not pages or len(pages) > 20:
        raise TutorError('Add between one and twenty video pages')
    http = http or httpx.Client(follow_redirects=True)
    videos, problems = {}, []
    for page in pages:
        _public_https(page)
        reply = None
        for attempt in range(2):  # a busy publisher site gets one more try
            try:
                reply = http.get(page, headers=AGENT, timeout=45)
                reply.raise_for_status()
                break
            except httpx.HTTPError:
                reply = None
                if not attempt:
                    time.sleep(2)
        if reply is None:
            problems.append(f'{page} could not be opened')
            continue
        for src in EMBED.findall(reply.text):
            video = parse(src.replace('&amp;', '&'))
            if video:
                videos.setdefault((video['provider'], video['video_id']), video)
    topics = [t for t in db.find('topics', subject_id=subject_id) if not t.get('archived')]
    numbered = {}
    for topic in topics:
        numbered.setdefault(lesson_number(topic['title']), []).append(topic)
    matched, unmatched = 0, []
    with db.transaction(kind='videos.found') as tx:
        tx.update('subjects', subject_id, {'video_pages': pages})
        for video in videos.values():
            title = _title(http, video)
            lessons = numbered.get(lesson_number(title)) or []
            if not title or len(lessons) != 1:
                unmatched.append(title or video['video_id'])
                continue
            topic = lessons[0]
            existing = tx.find('topic_videos', topic_id=topic['id'])
            if existing and existing[0]['source'] in ('manual', 'hidden'):
                continue  # a grown-up's choice for this lesson stays
            row = {'topic_id': topic['id'], 'title': title, 'source': 'found', 'found_at': _now(), **video}
            if existing:
                tx.update('topic_videos', existing[0]['id'], row)
            else:
                tx.insert('topic_videos', {'id': f"video-{topic['id']}", **row})
            matched += 1
    return {'pages': pages, 'videos': len(videos), 'matched': matched, 'unmatched': unmatched[:20], 'problems': problems}


def set_for_topic(db, topic_id, url=None, hidden=False, http=None):
    """A grown-up's own video for one lesson, or none at all."""
    if not db.get('topics', topic_id):
        raise TutorError('Choose a lesson from this curriculum')
    video = None
    if not hidden:
        video = parse(url)
        if not video:
            raise TutorError('Paste a Vimeo or YouTube link to the video')
    title = _title(http or httpx.Client(follow_redirects=True), video) if video else None
    row = {'topic_id': topic_id, 'source': 'hidden' if hidden else 'manual', 'title': title, 'found_at': _now(),
           **(video or {'provider': 'vimeo', 'video_id': '', 'key': None})}
    with db.transaction(kind='videos.lesson') as tx:
        existing = tx.find('topic_videos', topic_id=topic_id)
        if existing:
            tx.update('topic_videos', existing[0]['id'], row)
        else:
            tx.insert('topic_videos', {'id': f'video-{topic_id}', **row})
    return for_topic(db, topic_id)


def clear_for_topic(db, topic_id):
    """Back to whatever the video pages found."""
    with db.transaction(kind='videos.lesson_cleared') as tx:
        for row in tx.find('topic_videos', topic_id=topic_id):
            tx.delete('topic_videos', row['id'])
