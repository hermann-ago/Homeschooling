"""Version whitespace-only source corrections before narration, without generation."""
import copy
import json
import re

from . import guide, passages, script_review


def reading_requirements(manifest, correction):
    """Use only the recorded whitespace correction when rechecking source coverage."""
    result=copy.deepcopy(manifest)
    for old,new in (correction or {}).get('replacements',[]):
        if not old or re.sub(r'\s','',old)!=re.sub(r'\s','',new):
            raise ValueError('Invalid source-spacing provenance')
        for reading in result['readings']:
            reading['text']=' '.join(reading['text'].split()).replace(' '.join(old.split()),' '.join(new.split()))
    return result


def correct(ctx, row, expected_sha256, replacements):
    topic=ctx.store.get('topics',row['topic_id'])
    package=passages.load(ctx,topic)
    current=ctx.tutor.guide(topic,package)
    if not current or not current['current'] or current['guide_id']!=row['id'] or row['guide_sha256']!=expected_sha256:
        raise ValueError('The script changed. Reopen the current lesson before correcting its source spacing.')
    report=script_review.latest(ctx,row['id'])
    if script_review.status(ctx,row)['status']!='approved':
        raise ValueError('Review the script before making a formatting-only correction.')
    for old,new in replacements:
        if not old or old==new or re.sub(r'\s','',old)!=re.sub(r'\s','',new):
            raise ValueError('Only whitespace may change; source letters, punctuation and teaching text must stay intact.')
    original=json.loads(ctx.file_bytes(row['guide_path'],row.get('guide_file_sha256')))
    corrected=copy.deepcopy(original)
    def replace(text):
        for old,new in replacements:text=text.replace(old,new)
        return text
    for old,_ in replacements:
        if not any(s.get('kind')=='book' and old in s['text'] for s in original['sentences']):
            raise ValueError('Each correction must occur in the source reading, not in teacher text.')
    for sentence in corrected['sentences']:
        if sentence.get('kind')=='book':sentence['text']=replace(sentence['text'])
    for segment in corrected['segments']:
        if segment['type']=='read' and segment.get('text'):segment['text']=replace(segment['text'])
    for activity in corrected['activities']:
        if activity['kind']=='read_source':activity['content']['text']=replace(activity['content']['text'])
    context=copy.deepcopy(row.get('context_snapshot') or {})
    context['source_spacing']={'original_guide_id':row['id'],'replacements':replacements,
        'note':'Family-verified source typography only; original script and learner records retained.'}
    skill=ctx.store.get('subject_skills',row['skill_id']) if row.get('skill_id') else None
    with ctx.store.transaction(kind='tutor.source_spacing',summary='Saved a source-spacing revision before narration') as tx:
        saved=guide.save(tx,topic,package,corrected,model=row['model'],language=row['language'],
            skill=skill,learner_context=context)
    # This is an explicit source-formatting review, not a new AI assessment.
    script_review.save(ctx,saved,script_review.inputs(ctx,saved),{
        'findings':copy.deepcopy(report['data'].get('findings',[])),
        'based_on_review_id':report['id'],'source_spacing':context['source_spacing']},'formatting_review')
    return ctx.tutor.guide(topic,package)
