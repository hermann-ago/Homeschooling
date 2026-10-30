import copy,json
from tests.test_subject_analysis import setup_collection,provider,start,READING
from tutoring import book_companion


def test_source_map_refresh_is_free_pins_sources_and_preserves_previous_map(harness,monkeypatch):
    h=harness
    subject,collection,base=setup_collection(h)
    provider(h,monkeypatch)
    job,_=start(h,base)
    h.ctx.subject_analysis.process(job['id'])
    old=h.ctx.store.get('collection_analysis_jobs',job['id'])['map_id']
    frozen=copy.deepcopy(h.ctx.store.get('subject_maps',old))
    document=collection['books'][0]['document_id']
    endpoint=f"/api/subjects/{subject['id']}/book-companions/{document}"
    first=h.call('POST',endpoint).json()
    body=h.call('GET',endpoint+'/export').json()['contents']
    body['pages'][0]['text']+='\nA visually checked source amendment.'
    body['producer']='Synthetic visual source review'
    envelope={'contents':body,'content_sha256':book_companion.digest(body)}
    imported=h.call('POST',endpoint+'/import',files={'file':('review.json',json.dumps(envelope).encode(),'application/json')},
        data={'expected_revision':first['revision'],'source_review':'true','note':'Synthetic source review'})
    assert imported.status_code==200,imported.text
    from tutoring.map_review import reading_source
    section=frozen['data']['sections'][0]
    assert 'source amendment' not in str(reading_source(h.ctx,frozen,section['id']))
    def forbidden(*args,**kwargs):raise AssertionError('Local source-map review must not buy AI calls')
    monkeypatch.setattr(h.ctx.ai,'generate',forbidden)
    skill=h.call('GET','/api/material-skills').json()['skills'][0]
    assert h.call('PUT','/api/material-skills/'+skill['key'],json={
        'content':skill['content']+'\nReviewed local source rule.', 'expected_version':0}).status_code==200
    payload={'expected_map_id':old,'expected_version_id':collection['version_id'],
        'expected_source_hashes':{str(document):imported.json()['content_sha256']},'note':'Updated source evidence without regenerating proposals','decisions':[]}
    saved=h.call('POST',base+'/source-review',json=payload)
    assert saved.status_code==200,saved.text
    current=h.ctx.store.get('subject_maps',saved.json()['map_id'])
    assert current['id']!=old and h.ctx.store.get('subject_maps',old)==frozen
    assert 'source amendment' in str(reading_source(h.ctx,current,section['id']))
    assert current['data']['supersedes_map_id']==old
    assert not h.ctx.store.all('attempts') and not h.ctx.store.all('guides')
    payload['expected_source_hashes']={str(document):'stale'}
    assert h.call('POST',base+'/source-review',json=payload).status_code==400
