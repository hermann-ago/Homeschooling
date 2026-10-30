import copy,json
from tests.pdf_fixture import make_pdf
from tutoring.book_companion import native,digest,Companion


def setup(h):
    with h.ctx.store.transaction() as tx:
        child=tx.insert('children',{'name':'Practice learner'})
        subject=tx.insert('subjects',{'name':'Language Arts','child_id':child['id']})
    files=[('Part 1.pdf','combined','An adjective describes a noun.\nRead Chapter 1 of The Reader.\nWrite the word tree.',1),
           ('Part 2.pdf','combined','A verb describes an action.\nWrite the word run.',60),
           ('Reader.pdf','reference','Chapter 1.\nThe child walked along the quiet shore.',None),
           ('Official key.pdf','answer_key','PRIVATE OFFICIAL ANSWER 42\nPRIVATE OFFICIAL ANSWER 24',None)]
    selected=[]
    for i,(name,role,text,chapter) in enumerate(files):
        path=h.add_file(make_pdf([[text]]),'Books/'+name)
        selected.append({'key':str(i),'path':path,'role':role,'edition':'Synthetic edition','position':i,'is_main':i==0,
            **({'answer_for_keys':['0','1']} if role=='answer_key' else {})})
    url=f"/api/subjects/{subject['id']}/book-collection"
    response=h.call('PUT',url,json={'name':'Course and readers','expected_revision':0,'books':selected})
    assert response.status_code==200,response.text
    view=response.json();companions={};units=[];links=[]
    for b,(_,role,text,chapter) in zip(view['books'],files):
        path=h.drive/b['path'];body=native(path.read_bytes(),b['name'],role,b['edition'])
        page=body['pages'][0];page.update(status='checked',review_method='native_checked',issues=[],
            student_safe=role!='answer_key',teacher_material=role=='answer_key')
        if role=='combined':
            rule=text.split('\n')[0];page['reading_blocks']=[rule]
            body['exercises']=[{'id':f'task-{chapter}','reference':'','unnumbered':True,'chapter':chapter,'section':f'Lesson {chapter}',
                'pages':[1],'prompt':text.split('\n')[-1],'answer':None}]
            links.append({'document_id':b['document_id'],'source_item_id':f'task-{chapter}','status':'not_required',
                'instruction_quote':text.split('\n')[-1],'reason':'The synthetic task contains its own supplied word.'})
        if role=='answer_key':
            body['teacher_only']['answers']=[{'reference':'','chapter':n,'section':f'Lesson {n}','pages':[1],
                'answer':q,'evidence':q} for n,q in [(1,'PRIVATE OFFICIAL ANSWER 42'),(60,'PRIVATE OFFICIAL ANSWER 24')]]
        body=Companion.model_validate(body).model_dump();sha=digest(body)
        uploaded=h.call('POST',f"/api/subjects/{subject['id']}/book-companions/{b['document_id']}/import",
            files={'file':('book.json',json.dumps({'content_sha256':sha,'contents':body}).encode(),'application/json')},data={'expected_revision':0})
        assert uploaded.status_code==200,uploaded.text
        companions[str(b['document_id'])]=sha
        if role!='answer_key':
            units.append({'document_id':b['document_id'],'first_page':1,'last_page':1,'overview':'A source-bound synthetic section.',
                'concepts':[{'title':'Source reading','explanation':'Read the original source passage.','objective':'Read the supplied passage.',
                    'evidence':[{'page':1,'quote':text.split('\n')[0] if role=='combined' else 'The child walked along the quiet shore.'}]}]})
    key=view['books'][3];part1=view['books'][0];part2=view['books'][1];reader=view['books'][2]
    rel=[{'from_document_id':key['document_id'],'to_document_id':p['document_id'],'relationship':'official_key','source_page':1,
        'source_quote':'PRIVATE OFFICIAL ANSWER 42','target_pages':[1],'explanation':'The official key is explicitly assigned to both exact editions.'} for p in (part1,part2)]
    rel.append({'from_document_id':part1['document_id'],'to_document_id':reader['document_id'],'relationship':'independent_reading',
        'source_page':1,'source_quote':'Read Chapter 1 of The Reader.','target_pages':[1],'explanation':'The course explicitly assigns this reader chapter.'})
    payload={'expected_version_id':view['version_id'],'expected_companions':companions,'producer':'Codex synthetic source review',
        'overview':'A course, its reader and its shared official key.','note':'All synthetic source references were checked without generation.',
        'units':units,'links':links,'relationships':rel}
    return subject,url,payload


def test_codex_map_import_is_free_source_bound_private_and_idempotent(harness,monkeypatch):
    h=harness
    def forbidden(*args,**kw):raise AssertionError('Offline material import must not buy generation')
    monkeypatch.setattr(h.ctx.ai,'generate',forbidden)
    subject,url,p=setup(h)
    before={t:copy.deepcopy(h.ctx.store.all(t)) for t in ('topics','guides','attempts','tutor_sessions','scheduled_slots')}
    def upload(body):return h.call('POST',url+'/import-map',files={'file':('source-map.json',json.dumps(body).encode(),'application/json')})
    saved=upload(p);assert saved.status_code==200,saved.text
    mid=saved.json()['map_id'];public=h.call('GET','/api/subject-maps/'+mid)
    assert h.ctx.files.resolve(saved.json()['source_file']['file_path']).is_file()
    assert public.status_code==200,public.text
    assert 'PRIVATE OFFICIAL ANSWER' not in public.text
    assert len(public.json()['book_relationships'])==1
    assert all(e['answer_link_status']=='linked' for e in public.json()['exercises'])
    status=h.call('GET',url+'/analysis').json()['jobs'][0]
    assert status['provider']=='codex' and status['spending']['used_usd']==0
    assert upload(p).json()['map_id']==mid
    assert before=={t:h.ctx.store.all(t) for t in before}
    broken=copy.deepcopy(p);broken['units'][0]['concepts'][0]['evidence'][0]['quote']='A fabricated source quotation.'
    assert upload(broken).status_code==400
    broken=copy.deepcopy(p);broken['expected_companions'][next(iter(broken['expected_companions']))]='stale'
    assert upload(broken).status_code==400
    assert len(h.ctx.store.all('subject_maps'))==1


def test_explicit_pending_source_import_never_certifies_unchecked_pages(harness):
    h=harness;subject,url,p=setup(h)
    book=h.call('GET',url).json()['books'][0]
    from tutoring.book_companion import row_id
    with h.ctx.store.transaction() as tx:
        row=tx.get('book_companions',row_id(book['sha256'],book['role']))
        body=copy.deepcopy(row['data']);body['pages'][0].update(status='needs_review',issues=['An unchecked diagram.'],student_safe=True)
        sha=digest(body);tx.update('book_companions',row['id'],{'data':body,'content_sha256':sha})
    p['expected_companions'][str(book['document_id'])]=sha
    def upload(body):return h.call('POST',url+'/import-map',files={'file':('partial.json',json.dumps(body).encode(),'application/json')})
    assert upload(p).status_code==400
    p['allow_pending_sources']=True
    assert upload(p).status_code==400 # A concept still quotes an unchecked page.
    p['units'][0]['concepts']=[]
    p['relationships']=[r for r in p['relationships'] if r['relationship']=='official_key']
    p['links']=[l for l in p['links'] if l['document_id']!=book['document_id']]
    result=upload(p);assert result.status_code==200,result.text
    assert result.json()['coverage']['complete'] is False
    assert result.json()['coverage']['pending_pages']==1
    public=h.call('GET','/api/subject-maps/'+result.json()['map_id']).json()
    assert public['coverage']['checked_pages']==3
    assert not next(e for e in public['exercises'] if e['document_id']==book['document_id'])['student_safe']
    assert not h.call('GET',url).json()['knowledge_available']
    reading=h.call('GET',f"/api/subject-maps/{result.json()['map_id']}/reading/{public['sections'][0]['id']}")
    assert reading.status_code==200,reading.text
    assert reading.json()['pages']==[]
