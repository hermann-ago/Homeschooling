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
