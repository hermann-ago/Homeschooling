import copy
import pytest
from tests.test_interactive import prepare


def test_source_spacing_versions_reading_without_rewriting_teacher_or_learner_history(harness,monkeypatch):
    h=harness;s,g=prepare(h,monkeypatch)
    row=copy.deepcopy(h.ctx.store.get('guides',g['guide_id']))
    original=h.ctx.file_bytes(row['guide_path'])
    before={t:copy.deepcopy(h.ctx.store.all(t)) for t in ('attempts','tutor_sessions','lesson_playback','activity_responses')}
    monkeypatch.setattr(h.ctx.ai,'generate',lambda *a,**k:pytest.fail('Source spacing must not buy generation'))
    url=f"/api/tutor/guides/{row['id']}/source-spacing"
    for body in ({'expected_sha256':'0'*64,'replacements':[['Genghis Khan','Genghis  Khan']]},
                 {'expected_sha256':g['passage_sha256'],'replacements':[['tribes','tribe']]},
                 {'expected_sha256':g['passage_sha256'],'replacements':[['Let us','Let  us']]}):
        assert h.call('POST',url,json=body).status_code==400
    body={'expected_sha256':g['passage_sha256'],'replacements':[['Genghis Khan','GenghisKhan']]}
    result=h.call('POST',url,json=body,key='source-spacing-once')
    assert result.status_code==200,result.text
    new=result.json()
    assert new['guide_id']!=row['id'] and new['model']==g['model'] and new['current']
    assert len(new['sentences'])==len(g['sentences'])
    for old,changed in zip(g['sentences'],new['sentences']):
        if old.get('kind')!='book':assert changed==old
        assert ''.join(changed['text'].split())==''.join(old['text'].split())
    assert new['script_review']['status']=='approved' and new['script_review']['method']=='formatting_review'
    assert h.call('POST',url,json=body,key='source-spacing-once').json()==new
    assert h.ctx.store.get('guides',row['id'])==row and h.ctx.file_bytes(row['guide_path'])==original
    assert before=={t:h.ctx.store.all(t) for t in before}
    assert h.call('POST',url,json=body,role='tutor').status_code==403


def test_corrected_source_coverage_keeps_tasks_and_rejects_changed_letters():
    from tutoring.source_spacing import reading_requirements
    manifest={'readings':[{'text':'A\nnimal fi  cou imóvel.'}],'tasks':[{'instruction':'Write your answer.'}]}
    result=reading_requirements(manifest,{'replacements':[['A nimal','Animal'],['fi cou','ficou']]})
    assert result['readings'][0]['text']=='Animal ficou imóvel.'
    assert manifest['readings'][0]['text']=='A\nnimal fi  cou imóvel.'
    assert result['tasks']==manifest['tasks']
    with pytest.raises(ValueError):reading_requirements(manifest,{'replacements':[['Animal','Animals']]})
