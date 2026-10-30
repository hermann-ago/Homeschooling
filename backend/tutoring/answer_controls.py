"""Public book answer formats, including conservative legacy-source adapters.

Never inspect a key or solve a question to choose an input control. Ambiguous
layouts stay text answers until a source inventory supplies explicit metadata.
"""
import re

from .activities import QuestionContent


def binary_language(text):
    if re.search(r'verdadeir[oa]s?\s*(?:ou|/)\s*fals[oa]s?', text, re.I):
        return 'pt'
    if re.search(r'true\s*(?:or|/)\s*false', text, re.I):
        return 'en'
    return None


def binary_subitems(exercise):
    """Adapt a legacy multi-statement inventory without solving its questions.

    Only an explicit binary instruction followed by complete separate lines is
    unambiguous. Wrapped/uncertain layouts remain unchanged for source review.
    Each derived quote keeps the shared original instruction and exact item.
    """
    lines=[line.strip() for line in (exercise.get('prompt') or '').splitlines() if line.strip()]
    if len(lines)<3 or not binary_language(lines[0]):return [exercise]
    if not all(re.search(r'[.!?][”\"\']?$',line) for line in lines[1:]):return [exercise]
    portuguese=binary_language(lines[0])=='pt'
    return [{**exercise,'id':f"{exercise['id']}:statement-{i}",
             'reference':f"{exercise.get('reference') or ''} · {i}".strip(),
             'prompt':lines[0]+'\n'+line,'answer_format':'true_false',
             'choices':[{'id':'true','label':'Verdadeiro' if portuguese else 'True'},
                        {'id':'false','label':'Falso' if portuguese else 'False'}]}
            for i,line in enumerate(lines[1:],1)]


def book_controls(exercise):
    form = exercise.get('answer_format') or 'text'
    choices = exercise.get('choices') or []
    if form == 'text' and choices:
        form = 'single_choice'
    if form == 'text':
        prompt = exercise.get('prompt') or ''
        heading = (exercise.get('section') or '') + '\n' + prompt
        # Catalog entries already identify individual original exercises. Only
        # explicit directions identify a binary question; its answer is irrelevant.
        binary = binary_language(heading)
        portuguese = binary == 'pt'
        if binary:
            # Uppercase A./B./C. section headings are not question subparts.
            if (len(re.findall(r'(?m)^\s*\d+[.)]\s+\S',prompt)) > 1
                    or len(re.findall(r'(?m)^\s*[a-z][.)]\s+\S',prompt)) > 1
                    or len(binary_subitems({**exercise,'id':exercise.get('id') or 'source'})) > 1):
                return {}
            form = 'true_false'
            choices = [{'id':'true','label':'Verdadeiro' if portuguese else 'True'},
                       {'id':'false','label':'Falso' if portuguese else 'False'}]
        elif re.search(r'multiple.choice|choose.*(?:answer|option)|select.*(?:answer|option)|m[úu]ltipla.escolha|alternativa', heading, re.I):
            # Only unambiguous one-line options A..L in original order. Wrapped
            # options, subparts and unclear extraction require explicit metadata.
            section = (exercise.get('section') or '').strip()
            lines = [line.strip() for line in prompt.splitlines() if line.strip() and line.strip()!=section]
            options = [i for i,line in enumerate(lines) if re.match(r'^[Aa][.)]\s+\S',line)]
            tail = lines[options[0]:] if options else []
            labels = [re.match(r'^([A-La-l])[.)]\s+\S',line) for line in tail]
            if (2 <= len(tail) <= 12 and all(labels)
                    and [m[1].upper() for m in labels] == list('ABCDEFGHIJKL'[:len(labels)])):
                form = 'multiple_select' if re.search(r'select all|choose all|todas as alternativas',heading,re.I) else 'single_choice'
                choices = [{'id':m[1],'label':line} for m,line in zip(labels,tail)]
    if form == 'text':
        return {}
    content = QuestionContent(prompt=exercise.get('prompt') or 'Original book task',
                              answer_format=form, choices=choices)
    return {'answer_format':content.answer_format, 'choices':[c.model_dump() for c in content.choices]}
