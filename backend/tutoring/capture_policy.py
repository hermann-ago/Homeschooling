"""Keep source comprehension separate from inspecting handwriting."""
import re

PREPARATION_INSTRUCTIONS = '''Spelling and accent tasks accept typed text as spelling evidence: use evidence_requirement spelling,
response_modes text with optional photo; never require a photo for a typed spelling answer.
Device dictation cannot establish spelling. Written methods, handwriting and diagrams still need
their relevant steps or visual evidence rather than only a final answer.
These capture rules take precedence over conflicting older subject instructions or review_feedback.'''


def direct_text_capture(content):
    return bool('text' in content.get('response_modes',[]) and (
        content.get('evidence_requirement')=='spelling' or
        content.get('matching') and content.get('evidence_requirement','answer')=='answer'))


def answer_only_task(prompt, answer_format='text'):
    text = re.sub(r'\s+', ' ', prompt or '').casefold()
    # Never relax a task that explicitly tests the physical marks or spelling.
    if re.search(r'caligraf|handwriting|ortograf|spelling|ditado|dictation|copi|copy|sublin|underline|circule|circle|desenh|diagram|mostre.*cálculo|show.*work', text):
        return False
    if answer_format in ('true_false', 'single_choice', 'multiple_select'):
        return True
    return bool(re.search(r'lacuna|fill.*blank', text) and
        re.search(r'(palavras?|expressões).*d[oe] texto|(?:words?|phrases?).*(?:from|in) (?:the )?(?:text|passage|story)', text))


def task_content(content, task):
    """Only a checked task can correct an over-broad generated handwriting gate."""
    prompt=re.sub(r'\s+',' ',task.get('instruction') or task.get('prompt') or '').casefold()
    accents=bool(re.search(r'(?:coloque|ponha|adicione|complete|corrija).*\b(?:til|acento|acentos|acentuação)\b|(?:add|place|correct).*(?:accent|diacritic)',prompt))
    if content.get('evidence_requirement') in ('handwriting','spelling') and accents and not re.search(r'caligraf|handwriting|copi|copy|desenh|diagram',prompt):
        return {**content,'evidence_requirement':'spelling',
            'response_modes':list(dict.fromkeys(['text',*[mode for mode in content.get('response_modes',[]) if mode not in ('device_dictation','written_steps')]]))}
    if content.get('evidence_requirement') == 'handwriting' and answer_only_task(task.get('instruction') or task.get('prompt'), task.get('answer_format', 'text')):
        return {**content, 'evidence_requirement': 'answer',
            'response_modes': list(dict.fromkeys(['text', 'device_dictation', *(content.get('response_modes') or [])]))}
    return content


def activity_content(ctx, action):
    original = dict(action.get('activity_content') or {})
    if original.get('evidence_requirement') == 'spelling':
        original['response_modes']=list(dict.fromkeys(['text',*[mode for mode in original.get('response_modes',[]) if mode not in ('device_dictation','written_steps')]]))
    # Each exercise's evidence is what its script declared from the original page.
    return original


def answer_recheck_available(ctx, db, action, response):
    target=activity_content(ctx,action).get('evidence_requirement')
    return bool(response['status'] == 'parent_review' and response['method'] in ('photo','typed','written_steps')
        and not response.get('evidence_ids') and response.get('confirmed_text')
        and not db.get('lesson_dialogue', response.get('message_id'))
        and target in ('answer','spelling'))
