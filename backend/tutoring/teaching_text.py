"""Explicit family corrections to teacher wording, preserving the lesson's work."""
import copy
import json

from . import guide, passages, script_review
from .content_responsibility import TEACHING_POLICY
from .passages import split_sentences
from .activities import validate_activity


def correct(ctx, row, expected_sha256, replacements):
    topic = ctx.store.get('topics', row['topic_id'])
    package = passages.load(ctx, topic)
    current = ctx.tutor.guide(topic, package)
    if not current or current['guide_id'] != row['id'] or row['guide_sha256'] != expected_sha256:
        raise ValueError('The script changed. Reopen the lesson before correcting teacher wording.')
    from . import skills, visual_source, source_annotations, family_skill, library_materials
    subject = ctx.store.get('subjects', topic['subject_id'])
    skill = skills.packet(ctx.store, subject)
    frozen = row.get('context_snapshot') or {}
    family = family_skill.packet(ctx.store, subject['child_id'])
    book = library_materials.book_for(ctx.store, topic['subject_id'])
    if book:
        common = family_skill.current(ctx.store)
        family = {**family, 'sha256': family_skill.digest(common['content'], {})}
    if (row['source_sha256'] != package['passage_sha256'] or row['skill_sha256'] != skill['sha256']
            or not visual_source.current(ctx, row, topic)
            or (frozen.get('source_annotations') or []) != source_annotations.packet(ctx.store, topic)
            or (frozen.get('family_tutoring') or {}).get('sha256') != family['sha256']):
        raise ValueError('The source or teaching instructions changed. Prepare from the current material first.')
    report = script_review.latest(ctx, row['id'])
    if not report or report['status'] != 'approved':
        raise ValueError('Review the original script before making a teacher-wording correction.')
    original = json.loads(ctx.file_bytes(row['guide_path'], row.get('guide_file_sha256')))
    edited = copy.deepcopy(original)
    activities = guide.guide_activities(edited)
    changed = {}
    for old, new in replacements:
        matches = [a for a in activities if a['kind'] in ('introduce', 'explain_or_observe', 'close_lesson')
                   and a['content'].get('text') == old and a.get('origin') != 'required_book']
        if len(matches) != 1 or not new.strip() or old == new:
            raise ValueError('Each correction must match one complete teacher explanation, opening or closing.')
        activity = matches[0]
        new_content = validate_activity(activity['kind'], {**activity['content'], 'text': new})
        new = new_content['text']
        first, last = activity['start_sentence'], activity['end_sentence']
        sentences = split_sentences(new)
        if len(sentences) != last - first + 1:
            raise ValueError('Keep the same sentence count so saved work and reading positions remain valid.')
        for sentence, replacement in zip(edited['sentences'][first:last + 1], sentences):
            if sentence.get('kind') == 'book':
                raise ValueError('Original book text cannot be edited through teacher wording.')
            sentence['text'] = replacement['text']
        segments = [s for s in edited['segments'] if s['type'] in ('intro', 'explain', 'recap') and s.get('text') == old]
        if len(segments) != 1:
            raise ValueError('This teaching activity cannot be corrected without rebuilding its script.')
        segments[0]['text'] = new
        activity['content'] = new_content
        changed[activity['id']] = (old, new, activity['content'])
    edited['activities'] = activities
    context = copy.deepcopy(row.get('context_snapshot') or {})
    context['teaching_text_revision'] = {'original_guide_id': row['id'], 'replacements': replacements,
        'policy': TEACHING_POLICY, 'note': 'Explicit family correction of teacher wording; original source and learner work retained.'}
    # Preserve the original authoring snapshot as provenance; only this revision's
    # teacher words change. The original guide and recordings remain archived.
    # A new editorial policy changes the shared cache identity without changing
    # the selected pages. Publish the explicit correction under today's identity.
    if book:
        from .lesson_context import preparation
        shared = library_materials.neutral_context(ctx, preparation(ctx, subject['child_id'], topic, package))
        if frozen.get('visual_source'):
            shared['subject_sources'].pop('page_structure', None)
        context['library_material_key'] = library_materials.key(ctx, topic, package, row['language'], skill, shared)
        context['library_shared_policy'] = library_materials.VERSION
    sessions = []
    with ctx.store.transaction(kind='tutor.teaching_text', summary='Applied family-requested teacher wording; kept learner work and lesson position') as tx:
        saved = guide.save(tx, topic, package, edited, model=row['model'], language=row['language'],
                           skill=skill, learner_context=context)
        for playback in tx.find('lesson_playback', guide_id=row['id']):
            session = tx.get('tutor_sessions', playback['id'])
            if not session or session['status'] not in ('active', 'unfinished'):
                continue
            for action in tx.find('lesson_actions', session_id=session['id']):
                if action['action_id'] not in changed or action['status'] != 'pending':
                    continue
                old, new, content = changed[action['action_id']]
                tx.update('lesson_actions', action['id'], {'prompt': new,
                    'next_prompt': new if action.get('next_prompt') == old else action.get('next_prompt'),
                    'activity_content': copy.deepcopy(content)})
                for interaction in tx.find('activity_interactions', session_id=session['id'], activity_id=action['action_id']):
                    if interaction.get('prompt') == old:
                        tx.update('activity_interactions', interaction['id'], {'prompt': new})
            navigation = copy.deepcopy(playback.get('navigation_state') or {})
            for key, position in navigation.get('positions', {}).items():
                if isinstance(position, dict) and position.get('track_id'):
                    navigation['positions'][key] = {'sentence_index': position.get('sentence_index')}
            tx.update('lesson_playback', playback['id'], {'guide_id': saved['id'],
                'narration_cursor': None, 'navigation_state': navigation})
            tx.touch('tutor_sessions', session['id'])  # invalidate stale clients
            sessions.append(session['id'])
    script_review.save(ctx, saved, script_review.inputs(ctx, saved), {
        'findings': copy.deepcopy(report['data'].get('findings', [])),
        'based_on_review_id': report['id'], 'teaching_text_revision': context['teaching_text_revision']}, 'family_wording_review')
    if book and context.get('library_material_key'):
        library_materials.publish_guide(ctx, book, context['library_material_key'], saved, edited)
    return {**ctx.tutor.guide(topic, package), 'updated_sessions': sessions}
