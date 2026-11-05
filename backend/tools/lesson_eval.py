"""Score prepared lessons against hand-written expectations. No API calls.

An eval folder (tmp/eval/<name>/, gitignored: it holds book pages and learner
context) has the exported packet.json, source.pdf and a compiled guide
(before-guide.json, or any saved/imported guide). Expectations are read from
expected.json in that folder, else from docs/plans/eval/<name>.json:

    {"reading":   [{"starts": "first words", "ends": "last words"}],
     "exercises": [{"id": "p91-A3", "snippet": "words from the item", "answer": "key answer",
                    "page": 106, "number": 3}],
     "ignore_patterns": ["chapter3acommonstragedy[0-9]*"],
     "notes": "anything a reviewer should know"}

Reading spans are the passages that must be read aloud in full; coverage is
measured against the packet's PDF text layer when the span is found there.
`ignore_patterns` remove running headers the reader rightly skips; they match
the compacted reference (lowercase letters and digits, no spaces).
Exercise snippets are a few key terms from each original item that survive
paraphrase (prompts are often rewritten as teacher speech); an activity
citing the item's PDF `page` and exercise `number` also counts. Answers are optional and used only to detect
leaks next to the question.

    python tools/lesson_eval.py ../tmp/eval/history-380
    python tools/lesson_eval.py ../tmp/eval --all --guide before-guide.json

Metrics are evidence for a human review, not a quality score.
"""
import argparse
import json
import re
import sys
import unicodedata
from collections import Counter
from pathlib import Path

TEACHER = ('intro', 'explain', 'recap')
# Committed ground truth, used when an exported eval folder has no expected.json.
EXPECTATIONS = Path(__file__).resolve().parents[2] / 'docs/plans/eval'
QUOTES = str.maketrans({'‘': "'", '’': "'", '“': '"', '”': '"', '–': '-', '—': '-', '­': ''})


def words(text):
    text = unicodedata.normalize('NFKC', text or '').translate(QUOTES).casefold()
    return re.findall(r"[\w']+", text)


def compact(text):
    """Letters and digits only. PDF text layers split ligatures and drop caps
    ('ﬁ  sh', 'T he'), so spacing and punctuation are ignored when matching."""
    return ''.join(words(text)).replace("'", '')


def contains(haystack, needle):
    n = compact(needle)
    return bool(n) and n in compact(haystack)


CHUNK = 24


def matched_ratio(reference, text):
    """Share of the reference, in CHUNK-letter pieces, that appears in text."""
    ref, got = compact(reference), compact(text)
    pieces = [ref[i:i + CHUNK] for i in range(0, len(ref), CHUNK)]
    if not pieces:
        return None
    return sum(1 for p in pieces if p in got) / len(pieces)


def segment_text(segment):
    if segment['type'] == 'activity':
        return json.dumps(segment.get('content') or {}, ensure_ascii=False) + ' ' + (segment.get('text') or '')
    return segment.get('text') or ''


def span(reference, starts, ends):
    """The reference text from `starts` through `ends` (compacted), or None."""
    ref, s, e = compact(reference), compact(starts), compact(ends)
    i = ref.find(s)
    j = ref.find(e, i) if i >= 0 else -1
    return ref[i:j + len(e)] if j >= 0 else None


def located(activity, text, item):
    """A paraphrased prompt still counts when it cites the item's PDF page and number."""
    if 'page' not in item or 'number' not in item:
        return False
    pages = {r.get('page') for r in [*(activity.get('source_refs') or []),
                                    *((activity.get('content') or {}).get('source_refs') or [])]}
    return item['page'] in pages and str(item['number']) in words(text)


def questions(text):
    return [q.strip() for q in re.findall(r'[^.!?\n]*\?', text or '') if len(words(q)) >= 3]


TEACHER_KINDS = {'introduce': 'intro', 'close_lesson': 'recap', 'read_source': 'read'}


def segments_of(guide):
    """Saved guide files carry segments; API replies carry compiled activities."""
    if guide.get('segments'):
        return guide['segments']
    segments = []
    for a in guide.get('activities') or []:
        kind = TEACHER_KINDS.get(a['kind'])
        if kind is None and a['kind'] == 'explain_or_observe' and a.get('origin') != 'required_book':
            kind = 'explain'
        if kind:
            segments.append({'type': kind, 'text': a['content'].get('text')})
        else:
            segments.append({'type': 'activity', 'activity_kind': a['kind'], 'origin': a.get('origin'),
                             'content': a['content'], 'source_refs': a.get('source_refs') or []})
    return segments


def evaluate(guide, packet=None, expected=None, pdf_text=''):
    segments = segments_of(guide)
    expected = expected or {}
    reading = '\n'.join(s.get('text') or '' for s in segments if s['type'] == 'read')
    passage = ((packet or {}).get('package') or {}).get('passage') or ''
    explanations = [s for s in segments if s['type'] == 'explain']
    activities = [s for s in segments if s['type'] == 'activity']
    kinds = [s['type'] for s in segments]

    report = {
        'title': guide.get('title'), 'model': guide.get('model'),
        'segments': len(segments),
        'reading_words': len(words(reading)),
        'explanations': len(explanations),
        'explanation_words': sum(len(words(s.get('text'))) for s in explanations),
        'explanations_between_readings': sum(
            1 for i, k in enumerate(kinds) if k == 'explain' and 'read' in kinds[:i] and 'read' in kinds[i + 1:]),
        'activities': len(activities),
        'activities_by_origin': dict(Counter(s.get('origin') or 'unknown' for s in activities)),
        'activities_by_kind': dict(Counter(s.get('activity_kind') for s in activities)),
        'photo_only': sum(1 for s in activities if (s.get('content') or {}).get('response_modes') == ['photo']),
    }

    # Reading coverage: against the PDF text layer when the span is found there,
    # otherwise only whether its first and last words were read.
    spans = []
    for item in expected.get('reading', []):
        # Linked books (e.g. a read-together novel) are only in the PDF, not the passage.
        reference = span(passage, item['starts'], item['ends']) or span(pdf_text, item['starts'], item['ends'])
        for pattern in expected.get('ignore_patterns', []):
            reference = re.sub(pattern, '', reference) if reference else None
        ratio = matched_ratio(reference, reading) if reference else None
        spans.append({'starts': item['starts'][:40],
                      'coverage': round(ratio, 3) if ratio is not None else None,
                      'start_read': contains(reading, item['starts']),
                      'end_read': contains(reading, item['ends'])})
    report['reading_spans'] = spans
    if spans:
        measured = [s['coverage'] for s in spans if s['coverage'] is not None]
        report['reading_coverage'] = round(sum(measured) / len(measured), 3) if measured else None
        report['reading_spans_complete'] = sum(
            1 for s in spans if s['start_read'] and s['end_read'] and (s['coverage'] or 1) >= 0.95)

    # Exercises: every expected item appears in exactly one activity.
    texts = [segment_text(s) for s in activities]
    items = []
    for item in expected.get('exercises', []):
        hits = [i for i, t in enumerate(texts) if contains(t, item['snippet']) or located(activities[i], t, item)]
        leak = None
        if item.get('answer') and hits:
            first = activities[hits[0]]
            position = segments.index(first)
            before = segments[position - 1] if position and segments[position - 1]['type'] in TEACHER else None
            # A choice question lists its answer among the options; only text outside choices counts.
            content = dict(first.get('content') or {})
            content.pop('choices', None)
            nearby = json.dumps(content, ensure_ascii=False) + ' ' + (before.get('text') if before else '')
            leak = contains(nearby, item['answer'])
        items.append({'id': item['id'], 'found': len(hits), 'answer_leak': leak})
    report['exercise_items'] = items
    if items:
        report['exercises_found'] = sum(1 for i in items if i['found'])
        report['exercises_expected'] = len(items)
        report['exercises_duplicated'] = [i['id'] for i in items if i['found'] > 1]
        report['answer_leaks'] = [i['id'] for i in items if i['answer_leak']]
    # Items on shared exercise pages that belong to another lesson must not appear.
    others = expected.get('other_lessons_exercises', [])
    if others:
        report['exercises_from_other_lessons'] = [
            item['id'] for item in others
            if any(contains(t, item['snippet']) or located(activities[i], t, item) for i, t in enumerate(texts))]

    # Questions spoken in teacher narration never wait for an answer.
    report['narration_questions'] = [q for s in segments if s['type'] in TEACHER for q in questions(s.get('text'))]
    return report


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def run(folder, guide_name):
    folder = Path(folder)
    packet = load(folder / 'packet.json') if (folder / 'packet.json').exists() else None
    expected_path = next((p for p in (folder / 'expected.json', EXPECTATIONS / f'{folder.name}.json') if p.exists()), None)
    expected = load(expected_path) if expected_path else None
    pdf_text = ''
    if (folder / 'source.pdf').exists():
        from pypdf import PdfReader
        pdf_text = '\n'.join(page.extract_text() or '' for page in PdfReader(folder / 'source.pdf').pages)
    report = evaluate(load(folder / guide_name), packet, expected, pdf_text)
    report['eval'] = folder.name
    report['has_expectations'] = expected is not None
    if (folder / 'usage.json').exists():
        report['usage'] = load(folder / 'usage.json')
    if packet:
        report['prompt_characters'] = len(packet.get('prompt') or '')
    return report


def row(r):
    cov = r.get('reading_coverage')
    found = f"{r['exercises_found']}/{r['exercises_expected']}" if 'exercises_expected' in r else '—'
    return (f"| {r['eval']} | {'—' if cov is None else f'{cov:.0%}'} | {found} | {len(r.get('answer_leaks', []))} | "
            f"{len(r['narration_questions'])} | {r['explanations']} ({r['explanations_between_readings']} between) | "
            f"{r['explanation_words']} | {r['reading_words']} | {r['activities']} | {r.get('prompt_characters', '—')} |")


HEADER = ('| Eval | Reading covered | Exercises found | Answer leaks | Narration questions | Explanations | '
          'Explanation words | Reading words | Activities | Prompt chars |\n|---|---|---|---|---|---|---|---|---|---|')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('folder', type=Path)
    parser.add_argument('--guide', default='before-guide.json', help='guide file name inside each eval folder')
    parser.add_argument('--all', action='store_true', help='score every subfolder containing the guide')
    parser.add_argument('--json', action='store_true', help='print full reports as JSON')
    args = parser.parse_args(argv)
    folders = sorted(p for p in args.folder.iterdir() if (p / args.guide).exists()) if args.all else [args.folder]
    reports = [run(f, args.guide) for f in folders]
    sys.stdout.reconfigure(encoding='utf-8')
    if args.json:
        print(json.dumps(reports, ensure_ascii=False, indent=2))
    else:
        print(HEADER)
        print('\n'.join(row(r) for r in reports))


if __name__ == '__main__':
    main()
