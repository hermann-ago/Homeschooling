"""Narrow objective checks against the exact pinned, reviewed exercise key.

Never infer a key from reading prose or grade reasoning/written methods here.
Ambiguous wording, disputed keys and source exceptions remain tutor work.
"""
import re
import unicodedata


def _binary(value):
    if not isinstance(value, str):
        return None
    value = unicodedata.normalize('NFKC', value).casefold().strip()
    value = value.replace('’', "'")
    match = re.fullmatch(r"(?:(?:it is|it's|that is|that's|the answer is|a resposta e|a resposta é|e|é)\s+)?(true|false|verdadeiro|falso|v|f|t)[.!\s]*", value)
    return {'true': True, 'false': False, 'verdadeiro': True, 'falso': False, 'v': True, 'f': False, 't': True}.get(match[1]) if match else None


def checked_binary_assessment(snapshot, answer):
    """Return a verdict only for a reviewed true/false key and clear response."""
    source = snapshot.get('answer_source') or {}
    if (snapshot.get('status') != 'matched' or snapshot.get('answer_link_status') != 'reviewed'
            or snapshot.get('exception') or snapshot.get('issue') or snapshot.get('require_reasoning')
            or snapshot.get('evidence_requirement', 'answer') != 'answer'
            or not snapshot.get('source_sha256') or not source.get('pages')
            or not (source.get('teacher_key_id') or source.get('document_id'))):
        return None
    section = (snapshot.get('section') or '') + ' ' + (snapshot.get('prompt') or '')
    if not re.search(r'true\s+or\s+false|verdadeiro\s+ou\s+falso', section, re.I):
        return None
    expected, observed = _binary(snapshot.get('answer')), _binary(answer)
    if expected is None or observed is None:
        return None
    correct = expected == observed
    if (snapshot.get('language') or '').lower().startswith('pt'):
        return {'feedback': 'Isso mesmo! Sua resposta está correta.' if correct else
                'Vamos reler a afirmação inteira, prestando atenção a cada detalhe, e tentar novamente.',
            'result': 'Correct' if correct else 'Not yet', 'transcription': answer,
            'help': None, 'assistance_used': False,
            'follow_up': None if correct else 'A afirmação completa é verdadeira ou falsa?',
            'ready_to_continue': correct, 'concept': None, 'activity_requests': []}
    return {'feedback': 'Correct—your answer matches the checked book key.' if correct else
            'Not quite. Read the exact statement again, including who it refers to, then try true or false again.',
        'result': 'Correct' if correct else 'Not yet', 'transcription': answer,
        'help': None, 'assistance_used': False, 'follow_up': None if correct else 'Is the exact statement true or false?',
        'ready_to_continue': correct, 'concept': None, 'activity_requests': []}


def checked_ordering_assessment(snapshot, answer):
    """Compare ranks in printed order; never invert or infer an answer format."""
    source = snapshot.get('answer_source') or {}
    if (snapshot.get('answer_format') != 'ordering' or snapshot.get('status') != 'matched'
            or snapshot.get('answer_link_status') != 'reviewed' or snapshot.get('issue') or snapshot.get('exception')
            or snapshot.get('require_reasoning') or snapshot.get('evidence_requirement', 'answer') != 'answer'
            or not snapshot.get('source_sha256') or not source.get('document_id') or not source.get('pages')):
        return None
    expected = snapshot.get('answer')
    if not isinstance(expected, list) or not 2 <= len(expected) <= 40 or any(type(n) is not int for n in expected) or sorted(expected) != list(range(1, len(expected)+1)):
        return None
    text = unicodedata.normalize('NFKC', answer).strip()
    if not re.fullmatch(r'\d+(?:\s*[,;\s\-→]\s*\d+)+[.!]?', text):
        return None
    observed = [int(n) for n in re.findall(r'\d+', text)]
    if len(observed) != len(expected):
        return None
    correct = observed == expected
    portuguese = (snapshot.get('language') or '').startswith('pt')
    feedback = ('Isso mesmo! A sequência está correta.' if correct else
                'Vamos conferir novamente os números na ordem em que as frases estão impressas.') if portuguese else (
                'Correct! The sequence matches the printed statements.' if correct else
                'Check the numbers again in the order the statements are printed.')
    return {'feedback': feedback, 'result': 'Correct' if correct else 'Not yet', 'transcription': answer,
        'help': None, 'assistance_used': False, 'follow_up': None if correct else
        ('Qual é a sequência completa, na ordem das frases impressas?' if portuguese else 'What is the complete sequence in printed order?'),
        'ready_to_continue': correct, 'concept': None, 'activity_requests': []}


def _short_answer(value):
    """A number, a fraction or a few words, normalised; None when unreadable."""
    if not isinstance(value, str):
        return None
    text = unicodedata.normalize('NFKC', value).casefold().strip().replace('−', '-').replace('–', '-')
    text = re.sub(r'[.!]+$', '', text).strip()
    compact = text.replace(' ', '')
    if re.fullmatch(r'-?\d{1,3}(?:,\d{3})+(?:\.\d+)?', compact):
        compact = compact.replace(',', '')
    if re.fullmatch(r'-?\d+(?:\.\d+)?', compact):
        from decimal import Decimal
        return ('number', Decimal(compact))
    if re.fullmatch(r'-?\d+/\d+', compact) and not compact.endswith('/0'):
        from fractions import Fraction
        return ('number', Fraction(compact))
    words = ' '.join(re.findall(r"[^\W_]+", text))
    return ('words', words) if words else None


def checked_blanks_assessment(boxes, expected, observed, language=None):
    """Check one answer per box against the pinned key, or None if any box is unclear.

    Numbers and fractions compare by value; words must match the key exactly.
    A different word may still be an equivalent answer, so it goes to the tutor.
    """
    if not boxes or not expected or not isinstance(observed, dict) or len(expected) != len(boxes):
        return None
    results = {}
    for box, key in zip(boxes, expected):
        want, got = _short_answer(key), _short_answer(observed.get(box['id']))
        if want is None or got is None:
            return None
        if want[0] == 'number' and got[0] == 'number':
            results[box['id']] = want[1] == got[1]
        elif want == got:
            results[box['id']] = True
        elif want[0] == 'number':
            results[box['id']] = False  # a number was expected and something else was written
        else:
            return None
    right = sum(results.values())
    wrong = [box['label'] for box in boxes if not results[box['id']]]
    portuguese = (language or '').lower().startswith('pt')
    if not wrong:
        feedback = ('Isso mesmo!' if portuguese else 'Correct!') if len(boxes) == 1 else (
            f'Todas as {len(boxes)} certas!' if portuguese else f'All {len(boxes)} correct!')
    elif portuguese:
        feedback = f'{right} de {len(boxes)} certas. Confira de novo: ' + '; '.join(wrong)
    else:
        feedback = f'{right} of {len(boxes)} right. Take another look at: ' + '; '.join(wrong)
    return {'feedback': feedback, 'result': 'Correct' if not wrong else 'Partly correct' if right else 'Not yet',
        'transcription': None, 'help': None, 'assistance_used': False, 'follow_up': None,
        'ready_to_continue': not wrong, 'concept': None, 'activity_requests': [], 'blank_results': results}
