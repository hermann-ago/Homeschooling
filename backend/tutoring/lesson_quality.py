"""Source coverage for prepared scripts; never evidence of learner completion."""
import copy
import re

from .guide import GuideError


def normalized(text):
    return re.sub(r'\s+',' ',text or '').strip().casefold()


def checked_reading_text(text, page):
    """Recover typography only from an equivalent, checked page transcription.

    No dictionary guesses or generated corrections: letters, case and punctuation
    must agree after whitespace and original line-wrap hyphens are removed.
    Real printed hyphens remain unless that exact line-wrap has checked evidence.
    """
    def canonical(value):
        value=re.sub(r'(?<=[^\W\d_])-\s*\n\s*(?=[^\W\d_])','',value,flags=re.UNICODE)
        return re.sub(r'\s','',value)
    for element in page.get('elements',[]):
        candidate=element.get('text') or ''
        if (element.get('kind')=='text' and not element.get('issue') and candidate
                and canonical(candidate)==canonical(text)):
            return candidate
    return text


def task_reading_dependencies(task, manifest):
    """An explicit 'listen, then do' instruction waits AFTER its source reading.

    Do not infer dependencies from an unrelated diagram or a generic 'read' verb.
    Only complete, source-bound readings on this same page/document qualify.
    """
    instruction=normalized(task.get('instruction'))
    if not (re.search(r'\b(?:escute|ouça|listen)\b',instruction)
            and re.search(r'\b(?:agora|depois|then|after)\b',instruction)):
        return []
    return [r['id'] for r in manifest['readings'] if r['document_id']==task['document_id'] and r['page']==task['page']]


def task_matches(task,refs,tasks=()):
    quotes=[r.get('quote') or '' for r in refs if r.get('document_id')==task['document_id'] and r.get('page')==task['page']]
    target=normalized(task['instruction'])
    if target and (any(target in normalized(q) for q in quotes) or target in normalized(' '.join(quotes))):
        return True
    # A task can span several source sentences (listen, then mark letters).
    # A substantial exact excerpt may identify it when it is unique among the
    # original tasks on that page; never treat a vague word/page alone as a task.
    for quote in map(normalized,quotes):
        if len(quote)<20 or quote not in target:continue
        candidates=[t for t in tasks if t['document_id']==task['document_id'] and t['page']==task['page']
                    and quote in normalized(t['instruction'])]
        if len(candidates)==1:return True
    return False


def normalize_planned_readings(plan,manifest):
    """Accept the registered read_source tool only for the complete exact source.

    This reconciles two supported plan representations, never supplies an omitted
    poem or repairs its words. Unknown/missing/paraphrased text still fails.
    """
    if not isinstance(plan,dict):return plan
    plan=copy.deepcopy(plan)
    for i,segment in enumerate(plan.get('segments',[])):
        if not isinstance(segment,dict):continue
        registered=segment.get('type')=='activity' and segment.get('activity_kind')=='read_source'
        if not registered and (segment.get('type')!='read' or segment.get('source_block_id')):continue
        content=segment.get('content') or {} if registered else segment
        refs=[*(segment.get('source_refs') or []),*(content.get('source_refs') or [])]
        matches=[r for r in manifest['readings'] if normalized(content.get('text'))==normalized(r.get('text'))
            and content.get('document_id') in (None,r.get('document_id')) and content.get('page') in (None,r.get('page'))
            and all(ref.get('document_id') in (None,r.get('document_id')) and ref.get('page') in (None,r.get('page')) for ref in refs)]
        if len(matches)==1:
            source=matches[0]
            plan['segments'][i]={'type':'read','source_block_id':source['id'],
                'from':source['from'],'to':source['to']}
    return plan


def requirements(ctx,topic,passage):
    from .answer_controls import book_controls,binary_subitems
    from .book_companion import row_id
    from .books import READING_ROLES
    document=ctx.store.get('documents',topic.get('document_id'))
    result={'readings':[],'tasks':[],'checked_pages':[]}
    if not document:return result
    first,last=passage['pdf_pages']['start'],passage['pdf_pages']['end']
    sentences=passage['sentences']
    joined=' '.join(normalized(s['text']) for s in sentences)
    ends=[];pos=0
    for sentence in sentences:
        pos+=len(normalized(sentence['text']));ends.append(pos);pos+=1
    pages=[];tasks=[]
    for role in READING_ROLES:
        row=ctx.store.get('book_companions',row_id(document['sha256'],role))
        if not row:continue
        pages=[p for p in row['data']['pages'] if first<=p['page']<=last and p['status']=='checked'
               and p['student_safe'] and not p['teacher_material'] and not p['issues']]
        checked={p['page'] for p in pages}
        result['checked_pages']=sorted(checked)
        tasks=[t for t in row['data']['exercises'] if not t.get('issue') and set(t['pages']).issubset(checked)]
        break
    from .lesson_source_index import saved
    index=saved(ctx,topic)
    if index:
        checked=set(result['checked_pages'])
        extra=[p for p in index['data']['pages'] if p['page'] not in checked]
        pages+=extra
        result['indexed_pages']=sorted(p['page'] for p in extra)
        tasks += [t for t in index['data']['exercises'] if not set(t['pages']) & checked]
    for page in sorted(pages,key=lambda p:p['page']):
        for number,text in enumerate(page['reading_blocks']):
            quote=normalized(text);at=joined.find(quote)
            if not quote or at<0:
                if topic.get('start_at') or topic.get('stop_before'):continue
                raise GuideError('A source reading no longer matches the assigned passage. Review the source before preparing its script.')
            begin=next(i for i,end in enumerate(ends) if end>at)
            end=next(i for i,offset in enumerate(ends) if offset>=at+len(quote))
            checked_text=checked_reading_text(text,page)
            result['readings'].append({'id':f"p{page['page']}-reading-{number+1}",'page':page['page'],
                'document_id':document['id'],'text':checked_text,'from':begin,'to':end,
                **({'original_text':text,'typography':'equivalent_checked_transcription'} if checked_text!=text else {})})
    tasks=[part for task in tasks for part in binary_subitems(task)]
    ordered_tasks=sorted(tasks,key=lambda t:min(t['pages']))
    task_ids=[t.get('id') or f"p{min(t['pages'])}-task-{t['reference']}" for t in ordered_tasks]
    from collections import Counter
    counts=Counter(task_ids)
    occurrences=Counter()
    reserved_ids=set(task_ids)
    for task,identity in zip(ordered_tasks,task_ids):
        # Checked exercises can combine a shared stem with a later subitem or
        # transcribe a visual table. They need not be a contiguous excerpt of
        # the flattened reading passage. Only checked, public, in-range pages
        # reach this point; fresh inventories validate their quotes on import.
        if counts[identity]>1:
            if task.get('id'):
                raise GuideError('The source inventory repeats an explicit exercise identity. Review the source before preparation.')
            occurrences[identity]+=1
            candidate=f"{identity}-{occurrences[identity]}"
            while candidate in reserved_ids:
                occurrences[identity]+=1
                candidate=f"{identity}-{occurrences[identity]}"
            identity=candidate
            reserved_ids.add(identity)
        result['tasks'].append({'id':identity,
            'page':min(task['pages']),'document_id':document['id'],'reference':task['reference'],'instruction':task['prompt'],
            'answer_format':'text','choices':[],**book_controls(task)})
    return result


def resolve_readings(plan,manifest):
    """Source-block references insert original words, rather than AI paraphrases."""
    plan=copy.deepcopy(plan)
    sources={r['id']:r for r in manifest['readings']}
    for segment in plan.get('segments',[]):
        identity=segment.get('source_block_id')
        if not identity:continue
        if segment.get('type')!='read' or identity not in sources:
            raise GuideError('The script refers to an unknown checked reading block.')
        source=sources[identity]
        segment.update(text=source['text'],**{'from':source['from'],'to':source['to']},
            source_refs=[{'document_id':source['document_id'],'page':source['page'],'quote':source['text']}])
    return plan


def coherent_readings(plan):
    """Compile adjacent checked reading blocks into one learner turn.

    This runs only when preparing a new guide, after source validation/resolution.
    It never reprojects saved guides or crosses a teacher/learner activity. Keep
    every source identity and locator: page-local inventory units are provenance,
    not a request for another Continue click. Unchecked or discontinuous ranges
    retain their separate boundaries.
    """
    result=copy.deepcopy(plan)
    segments=[]
    for segment in result.get('segments',[]):
        previous=segments[-1] if segments else None
        checked=lambda s: bool(s and s.get('type')=='read' and s.get('source_block_id')
                               and s.get('text') and isinstance(s.get('from'),int)
                               and isinstance(s.get('to'),int))
        # A flattened extraction may put a heading and the story's first words
        # in the SAME source sentence. Distinct checked excerpts still form one
        # reading; their emitted text/identities, not a guessed sentence split,
        # are checked for completeness and duplication below.
        if (checked(previous) and checked(segment)
                and previous['from']<=segment['from']<=previous['to']+1
                and segment['to']>=previous['to']
                and len(previous['text'])+len(segment['text'])+1<=200000):
            previous.setdefault('source_block_ids',[previous['source_block_id']]).append(segment['source_block_id'])
            previous['text']+=' '+segment['text']
            previous['to']=segment['to']
            previous.setdefault('source_refs',[]).extend(segment.get('source_refs') or [])
        else:
            segments.append(segment)
    result['segments']=segments
    return result


def reflow(ctx,row,expected_sha256):
    """Version a layout-only compilation of an approved, unchanged script.

    Preserve the original guide and model. No teaching text, tasks, responses or
    assessments are generated. Existing sessions stay pinned to their old guide.
    """
    import json
    from . import guide,passages,script_review
    topic=ctx.store.get('topics',row['topic_id'])
    package=passages.load(ctx,topic)
    current=ctx.tutor.guide(topic,package)
    if not current or not current['current'] or current['guide_id']!=row['id'] or row['guide_sha256']!=expected_sha256:
        raise ValueError('The script changed. Reopen it before updating its reading layout.')
    if script_review.status(ctx,row)['status']!='approved':
        raise ValueError('Review the script before updating its reading layout.')
    original=json.loads(ctx.file_bytes(row['guide_path'],row.get('guide_file_sha256')))
    plan=coherent_readings(original)
    if plan['segments']==original['segments']:return current
    context=copy.deepcopy(row.get('context_snapshot') or {})
    manifest=context.get('source_requirements')
    if not manifest:raise ValueError('This script has no checked reading inventory to recompile.')
    built=guide.build(package['sentences'],plan)
    # Compare the spoken stream independently of changed sentence boundaries.
    if normalized(' '.join(s['text'] for s in original['sentences']))!=normalized(' '.join(s['text'] for s in built['sentences'])):
        raise ValueError('A layout update cannot alter the spoken script.')
    built['source_coverage']=validate(built,manifest)
    context['reading_flow']={'version':1,'original_guide_id':row['id'],
        'before':len(original['activities']),'after':len(built['activities'])}
    skill=ctx.store.get('subject_skills',row.get('skill_id')) if row.get('skill_id') else None
    prior=script_review.latest(ctx,row['id'])
    with ctx.store.transaction(kind='tutor.reading_flow',summary='Joined adjacent checked reading without changing teaching text') as tx:
        saved=guide.save(tx,topic,package,built,model=row['model'],language=row['language'],skill=skill,learner_context=context)
    script_review.save(ctx,saved,script_review.inputs(ctx,saved),{
        'findings':copy.deepcopy(prior['data'].get('findings',[])),
        'based_on_review_id':prior['id'],'reading_flow':context['reading_flow']},'layout_review')
    return ctx.tutor.guide(topic,package)


def bind_tasks(plan,manifest):
    """Only the checked source inventory can promote an activity to required work."""
    from .activities import requires_response
    for segment in plan.get('segments',[]):
        if segment.get('type')!='activity':continue
        refs=[*(segment.get('source_refs') or []),*((segment.get('content') or {}).get('source_refs') or [])]
        if any(task_matches(task,refs,manifest['tasks']) for task in manifest['tasks']):
            segment['origin']='required_book'
        matching=[task for task in manifest['tasks'] if task_matches(task,refs,manifest['tasks'])]
        form=(segment.get('content') or {}).get('matching')
        if form and matching:
            text=normalized(' '.join(t['instruction'] for t in matching))
            if any(normalized(item['label']) not in text for item in [*form['items'],*form['options']]):
                raise GuideError('Matching labels must come from the checked original task; no options were displayed.')
        if len(matching)==1 and segment.get('activity_kind')=='request_book_work':
            from .capture_policy import task_content
            segment['content']=task_content(segment.get('content') or {}, matching[0])
        if (len(matching)==1 and matching[0].get('answer_format','text')!='text'
                and requires_response(segment.get('activity_kind'),segment.get('content') or {})):
            # The book's checked public options take precedence over generated alternatives.
            task=matching[0];content=segment.get('content') or {}
            content.update(answer_format=task['answer_format'],choices=copy.deepcopy(task.get('choices') or []),
                response_modes=list(dict.fromkeys(['choice',*(content.get('response_modes') or ['text'])])))
            segment['content']=content
    return plan


def validate(built,manifest):
    """Check actual emitted words and waiting tasks before saving or buying audio."""
    readings=[a for a in built['activities'] if a['kind']=='read_source']
    emitted=' '.join(normalized(a['content']['text']) for a in readings)
    missing=[r for r in manifest['readings'] if normalized(r['text']) not in emitted]
    if missing:
        pages=', '.join(str(r['page']) for r in missing)
        raise GuideError(f'The script omitted or changed required reading on book page(s) {pages}. No voice was requested.',
                         reason='missing_required_reading')
    position=-1
    for reading in manifest['readings']:
        text=normalized(reading['text']);at=emitted.find(text)
        if at<position or emitted.count(text)!=1:
            raise GuideError('Required readings must appear once, in their original source order.',reason='required_reading_order')
        position=at
    missing_tasks=[];assigned=set()
    for task in manifest['tasks']:
        covered=False
        for index,activity in enumerate(built['activities']):
            if index in assigned or activity['kind'] in ('read_source','introduce','close_lesson'):continue
            refs=[*(activity.get('source_refs') or []),*(activity['content'].get('source_refs') or [])]
            covered=task_matches(task,refs,manifest['tasks'])
            if covered:
                dependencies=task_reading_dependencies(task,manifest)
                if any(not any(normalized(r['text']) in normalized(a['content']['text'])
                        for a in built['activities'][:index] if a['kind']=='read_source')
                        for r in manifest['readings'] if r['id'] in dependencies):
                    raise GuideError('A listening task must wait after its complete source reading, not before it.',
                                     reason='required_task_order')
                assigned.add(index);break
        if not covered:missing_tasks.append(task)
    if missing_tasks:
        refs=', '.join(f"{t['page']} / {t['reference']}" for t in missing_tasks)
        raise GuideError(f'The script is missing a waiting activity for book page / task {refs}. No voice was requested.',
                         reason='missing_required_task')
    return {'version':1,'checked_pages':manifest['checked_pages'],'indexed_pages':manifest.get('indexed_pages',[]),'required_readings':len(manifest['readings']),
            'readings_preserved':len(manifest['readings']), 'required_tasks':len(manifest['tasks']),
            'tasks_represented':len(manifest['tasks'])}
