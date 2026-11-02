import copy


def test_editable_material_skills_keep_versions_and_do_not_generate(harness,monkeypatch):
    h=harness
    def forbidden(*args,**kwargs):raise AssertionError('Editing skills must not generate content')
    monkeypatch.setattr(h.ctx.ai,'generate',forbidden)
    before={t:copy.deepcopy(h.ctx.store.all(t)) for t in ['guides','topics','attempts','tutor_sessions']}
    items=h.call('GET','/api/material-skills').json()['skills']
    assert {s['key'] for s in items}=={'book-json','material-links','script-review'}
    item=next(s for s in items if s['key']=='book-json')
    result=h.call('PUT','/api/material-skills/book-json',json={'content':item['content']+'\nA family instruction.','expected_version':0})
    assert result.status_code==200,result.text
    assert result.json()['version']==1
    again=h.call('GET','/api/material-skills').json()['skills'][0]
    assert {v['version'] for v in again['history']}=={0,1}
    assert h.call('PUT','/api/material-skills/book-json',json={'content':'Stale edit','expected_version':0}).status_code==409
    assert h.call('GET','/api/material-skills',role='tutor').status_code==403
    assert before=={t:h.ctx.store.all(t) for t in before}


def test_test_mode_skill_edits_leave_family_versions_and_files_unchanged(harness):
    h=harness
    item=h.call('GET','/api/material-skills').json()['skills'][0]
    h.call('PUT','/api/material-skills/'+item['key'],json={
        'content':item['content']+'\nSaved family rule.', 'expected_version':item['version']})
    before=copy.deepcopy(h.ctx.store.all('material_skills'))
    files={str(p.relative_to(h.drive)):p.read_bytes() for p in h.drive.rglob('*') if p.is_file() and p.suffix=='.md'}
    enabled=h.client.post('/api/test-mode',headers={'X-Homeschooling-Mode':'live'},json={'enabled':True})
    assert enabled.status_code==200,enabled.text
    token=enabled.json()['token']
    response=h.client.put('/api/material-skills/'+item['key'],headers={'X-Homeschooling-Mode':token},json={
        'content':item['content']+'\nDisposable testing rule.', 'expected_version':1})
    assert response.status_code==200,response.text
    assert h.ctx.store.all('material_skills')==before
    assert files=={str(p.relative_to(h.drive)):p.read_bytes() for p in h.drive.rglob('*') if p.is_file() and p.suffix=='.md'}
