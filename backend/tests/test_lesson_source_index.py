"""Automatic visual source preflight, separate from personalized scripts/evidence."""
import copy

import pytest

from tests.test_visual_source import whole_page, VISUAL
from tutoring import lesson_source_index as index, lesson_quality, lesson_context, visual_source, books
from tutoring.guide import GuideError


def source(h):
    seed,topic,package=whole_page(h)
    pdf,metadata=visual_source.prepare(h.ctx,topic,package,VISUAL)
    text=' '.join(s['text'] for s in package['sentences'])
    # An invented fixture's complete source is one protected reading.
    scan={'pages':[{'page':2,'text':text,'native_reliable':False,'student_safe':True,
        'teacher_material':False,'reading_blocks':[text],'elements':[]}], 'exercises':[],'answers':[]}
    return seed,topic,package,pdf,metadata,scan


@pytest.mark.parametrize('bad',['private','missing-page','paraphrase','invented-task'])
def test_uncertain_or_fabricated_source_stops_before_personalized_script(harness,monkeypatch,bad):
    h=harness;_,topic,package,pdf,metadata,scan=source(h)
    if bad=='private':scan['pages'][0]['teacher_material']=True
    if bad=='missing-page':scan['pages']=[]
    if bad=='paraphrase':scan['pages'][0]['reading_blocks']=['Words invented outside the source.']
    if bad=='invented-task':scan['exercises']=[{'reference':'1','pages':[2],'prompt':'A task not printed on this page.','kind':'activity'}]
    monkeypatch.setattr(h.ctx.ai,'generate',lambda *_a,**_k:copy.deepcopy(scan))
    with pytest.raises((GuideError,ValueError)):
        index.ensure(h.ctx,topic,package,pdf,metadata)
    assert index.saved(h.ctx,topic) is None and not h.ctx.store.all('guides')


def test_literal_reading_anchors_recover_an_omitted_transcription_without_changing_the_reply(harness,monkeypatch):
    h=harness;_,topic,package,pdf,metadata,scan=source(h)
    scan['pages'][0]['text']=''
    raw=copy.deepcopy(scan)
    monkeypatch.setattr(h.ctx.ai,'generate',lambda *_a,**_k:scan)
    result=index.ensure(h.ctx,topic,package,pdf,metadata)
    page=result['data']['pages'][0]
    assert page['text'] and page['reading_blocks'] and page['native_reliable'] is False
    assert scan==raw


def test_source_provider_failure_is_structured_and_preserves_saved_work(harness,monkeypatch):
    h=harness;_,topic,package,pdf,metadata,_=source(h)
    def unavailable(*args,**kwargs):raise ValueError('Synthetic provider quota is paused')
    monkeypatch.setattr(h.ctx.ai,'generate',unavailable)
    with pytest.raises(GuideError,match='inventory could not finish') as error:
        index.ensure(h.ctx,topic,package,pdf,metadata)
    assert error.value.reason=='source_inventory_failed'
    assert index.saved(h.ctx,topic) is None and not h.ctx.store.all('guides')


def test_distinct_unnumbered_tasks_get_stable_unique_preparation_identities(harness,monkeypatch):
    h=harness;_,topic,package,pdf,metadata,scan=source(h)
    scan['exercises']=[{'reference':'','unnumbered':True,'pages':[2],'prompt':prompt,'kind':'activity'}
        for prompt in ('The Mongols came from the north.','They lived in felt tents.')]
    monkeypatch.setattr(h.ctx.ai,'generate',lambda *_a,**_k:copy.deepcopy(scan))
    index.ensure(h.ctx,topic,package,pdf,metadata)
    tasks=lesson_quality.requirements(h.ctx,topic,package)['tasks']
    assert len({t['id'] for t in tasks})==2
    assert [t['instruction'] for t in tasks]==[t['prompt'] for t in scan['exercises']]
    assert lesson_quality.requirements(h.ctx,topic,package)['tasks']==tasks


def test_cached_inventory_probe_is_read_only_and_never_calls_provider(harness,monkeypatch):
    h=harness;_,topic,package,pdf,metadata,_=source(h)
    seen=[]
    def probe(prompt,**kwargs):
        seen.append(prompt)
        assert kwargs['schema'] is books.ScanResult and kwargs['pdf']==pdf
        return True
    monkeypatch.setattr(h.ctx.ai,'has_valid_cached_reply',probe)
    monkeypatch.setattr(h.ctx.ai,'generate',lambda *_a,**_k:pytest.fail('A preview must not buy source analysis'))
    assert index.cached_reply_available(h.ctx,topic,package,pdf,metadata)
    assert len(seen)==1 and index.saved(h.ctx,topic) is None


def test_source_tasks_accept_drop_caps_and_shared_stems_without_changing_signs():
    assert index.task_quote_supported('Work on the reading cards.','W ork on the reading cards.')
    page='Write each word in lowercase.\nANY | MANY | SOME'
    assert index.task_quote_supported('Write each word in lowercase.\nSOME',page)
    assert not index.task_quote_supported('Write each word in lowercase.\nINVENTED',page)
    assert not index.task_quote_supported('3 - 2 = 1','3 + 2 = 1')
