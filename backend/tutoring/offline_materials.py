"""Import checked source analysis produced in Codex, without a provider request."""
from typing import Literal
import json
from pydantic import BaseModel,ConfigDict,Field
from storage import layout
from storage.store import sha256_text
from . import books,book_companion
from .subject_analysis import Concept,Quote,VERSION,safe_pages,valid_quote


class Strict(BaseModel):
    model_config=ConfigDict(extra='forbid')


class Unit(Strict):
    document_id:int=Field(ge=1)
    first_page:int=Field(ge=1)
    last_page:int=Field(ge=1)
    overview:str=Field(max_length=1200)
    concepts:list[Concept]=Field(default_factory=list,max_length=10)


class Evidence(Quote):
    document_id:int=Field(ge=1)


class Link(Strict):
    document_id:int=Field(ge=1)
    source_item_id:str=Field(min_length=1,max_length=150)
    status:Literal['proposed','not_required','needs_review']
    evidence:list[Evidence]=Field(default_factory=list,max_length=5)
    instruction_quote:str=Field(default='',max_length=1000)
    reason:str=Field(min_length=1,max_length=650)


class Relationship(Strict):
    from_document_id:int=Field(ge=1)
    to_document_id:int=Field(ge=1)
    relationship:Literal['required_reading','read_together','independent_reading','official_key','reinforces']
    source_page:int=Field(ge=1)
    source_quote:str=Field(min_length=12,max_length=800)
    target_pages:list[int]=Field(min_length=1,max_length=500)
    explanation:str=Field(max_length=650)


class SourceMap(Strict):
    format:Literal['homeschooling.source-map']='homeschooling.source-map'
    format_version:Literal[1]=1
    expected_version_id:str
    expected_companions:dict[str,str]
    producer:str=Field(min_length=1,max_length=200)
    overview:str=Field(max_length=2400)
    note:str=Field(min_length=10,max_length=2000)
    allow_pending_sources:bool=False
    units:list[Unit]=Field(max_length=3000)
    links:list[Link]=Field(default_factory=list,max_length=10000)
    relationships:list[Relationship]=Field(default_factory=list,max_length=3000)


def save(ctx,tx,subject_id,payload):
    version=ctx.subject_analysis.version(subject_id)
    if version['id']!=payload.expected_version_id:raise ValueError('The source collection changed; export its latest identities')
    if any(j['status'] in ('running','queued') for j in tx.find('collection_analysis_jobs',collection_id=version['collection_id'])):
        raise ValueError('Finish or pause source preparation before importing a Codex map')
    plan=ctx.subject_analysis.plan(version,subject_id);sources=plan['sources'];bydoc={s['document_id']:s for s in sources}
    companions={};scans={};sections=[];units={};pages={};issues=[];pending_pages=0;checked_units=0
    for src in sources:
        row=tx.get('book_companions',book_companion.row_id(src['sha256'],src['role']))
        if not row or payload.expected_companions.get(str(src['document_id']))!=row['content_sha256']:
            raise ValueError('Import the exact companion JSON for every source before its Codex map')
        companions[str(src['document_id'])]=row['content_sha256'];scans[src['id']]=[]
        pending=sum(p['status']!='checked' for p in row['data']['pages'])
        unchecked={p['page'] for p in row['data']['pages'] if p['status']!='checked'}
        pending_pages+=pending
        if pending:issues.append(f"{src['name']}: {pending} PDF pages still require source review; their content is excluded from teaching evidence.")
        for first in range(1,src['pages']+1,books.UNIT_PAGES):
            last=min(first+books.UNIT_PAGES-1,src['pages'])
            cached=ctx.subject_analysis.cached_scan(src,{'first':first,'last':last})
            checked=all(p['status']=='checked' for p in row['data']['pages'][first-1:last])
            if (not cached or not checked) and not payload.allow_pending_sources:
                raise ValueError(f"Finish checking the source pages before importing this map: {src['name']}, PDF {first}-{last}")
            checked_units+=int(checked)
            data=book_companion.unit_data(row['data'],first,last)
            for page in data['pages']:
                if page['page'] in unchecked:page['student_safe']=False
            for item in [*data['exercises'],*data['answers']]:
                if any(n in unchecked for n in item['pages']):item['issue']=item.get('issue') or 'Source pages still require review'
            step={'source_id':src['id'],'first':first,'last':last};scans[src['id']].append((step,data))
            if src['role']=='answer_key':continue
            uid='source-unit-'+books.ident(src['sha256'],src['role'],first,last)
            units[(src['document_id'],first)]=uid
            pages[uid]=safe_pages(src,data)
    if set(payload.expected_companions)!=set(companions):raise ValueError('The map includes a book outside this exact collection')
    if len({(u.document_id,u.first_page) for u in payload.units})!=len(payload.units) or {(u.document_id,u.first_page) for u in payload.units}!=set(units):
        raise ValueError('Include each public source section exactly once, in eight-page units')
    for u in payload.units:
        src=bydoc[u.document_id];uid=units[(u.document_id,u.first_page)]
        if u.last_page!=min(u.first_page+books.UNIT_PAGES-1,src['pages']):raise ValueError('A source section has the wrong page boundaries')
        concepts=[]
        for i,item in enumerate(u.concepts):
            value=item.model_dump()
            if not all(valid_quote(q,pages[uid]) for q in value['evidence']):raise ValueError('A Codex concept needs literal checked student-page evidence')
            concepts.append({**value,'id':uid+f':concept:{i}','unit_id':uid,'document_id':src['document_id'],'sha256':src['sha256'],'status':'proposed'})
        sections.append({'id':uid,'source_id':src['id'],'document_id':src['document_id'],'sha256':src['sha256'],
            'pages':[u.first_page,u.last_page],'overview':u.overview,'concepts':concepts,'events':[],'issues':[]})
    job={'plan':plan};exercises,private=ctx.subject_analysis.exercises(job,scans,sources)
    inputs={(l.document_id,l.source_item_id):l for l in payload.links}
    if len(inputs)!=len(payload.links) or set(inputs)-{(e['document_id'],e['source_item_id']) for e in exercises}:
        raise ValueError('Each relationship must target a real companion exercise in this collection')
    links=[]
    for e in exercises:
        item=inputs.get((e['document_id'],e['source_item_id']))
        if not item:
            links.append({'exercise_id':e['id'],'status':'needs_review','evidence':[],'reason':'No verified dependency decision was supplied for this source exercise'})
            continue
        evidence=[]
        for q in item.evidence:
            first=((q.page-1)//books.UNIT_PAGES)*books.UNIT_PAGES+1;uid=units.get((q.document_id,first))
            if not uid or not valid_quote(q.model_dump(),pages[uid]):raise ValueError('A reading link lacks its exact checked source quote')
            evidence.append({'unit_id':uid,'page':q.page,'quote':q.quote})
        if item.status=='proposed' and not evidence:raise ValueError('A proposed prerequisite needs source evidence')
        if item.status=='not_required' and (not e['student_safe'] or len(books.norm(item.instruction_quote))<12 or not books.original_quote(e['prompt'],item.instruction_quote)):
            raise ValueError('Self-contained work requires its exact original instruction quote')
        links.append({'exercise_id':e['id'],'status':item.status,'evidence':evidence,'reason':item.reason,
            'source_instruction_quote':item.instruction_quote,'review_method':'codex_source_review'})
    relationships=[];private_relationships=[]
    for r in payload.relationships:
        src=bydoc.get(r.from_document_id);target=bydoc.get(r.to_document_id)
        if not src or not target or src['id']==target['id'] or not 1<=min(r.target_pages)<=max(r.target_pages)<=target['pages']:
            raise ValueError('A cross-book relationship identifies an invalid source or target range')
        row=tx.get('book_companions',book_companion.row_id(src['sha256'],src['role']))
        if not 1<=r.source_page<=src['pages'] or not books.original_quote(row['data']['pages'][r.source_page-1]['text'],r.source_quote):
            raise ValueError('A cross-book relationship must quote its original source instruction')
        if r.relationship=='official_key':
            from .collections import key_targets
            if src['role']!='answer_key' or target['id'] not in key_targets(src):raise ValueError('The key is not explicitly assigned to this exact source edition')
        elif src['role']=='answer_key' or target['role']=='answer_key':raise ValueError('Private key pages cannot become public reading dependencies')
        page=row['data']['pages'][r.source_page-1]
        if r.relationship!='official_key' and (page['teacher_material'] or page['status']!='checked'):
            raise ValueError('Public source links must not reveal private or unchecked content')
        (private_relationships if r.relationship=='official_key' else relationships).append({**r.model_dump(),'from_source_id':src['id'],'to_source_id':target['id']})
    concepts=[c for s in sections for c in s['concepts']]
    flags=sum(l['status']=='needs_review' for l in links)+sum(e['answer_link_status']=='needs_review' for e in exercises)+pending_pages
    identity=sha256_text([version['id'],payload.model_dump()]);jid='codex-materials-'+identity[:32];mid='subject-map-'+identity[32:]
    data={'analysis_version':VERSION,'collection_version_id':version['id'],'provider':'codex','model':'Codex source review',
        'producer':payload.producer,'material_skills':plan['material_skills'],'books':sources,'sections':sections,'concepts':concepts,
        'events':[],'overview':payload.overview,'connections':[],'book_relationships':relationships,'private_book_relationships':private_relationships,'exercises':exercises,'exercise_links':links,
        'issues':issues,'flagged_items':flags,'review_status':'proposed','private_answers':private,'source_review_note':payload.note,
        'source_review_ids':{s['id']:max(tx.find('book_source_reviews',sha256=s['sha256'],role=s['role']),key=lambda r:r['version'],default={}).get('id') for s in sources},
        'source_companion_hashes':companions,'source_readings':pages,'coverage':{'books':len(sources),'pages':sum(s['pages'] for s in sources),
        'sections':len(sections),'exercises':len(exercises),'complete':not pending_pages,'pending_pages':pending_pages,
        'checked_pages':sum(s['pages'] for s in sources)-pending_pages,'pending_exercises':sum(bool(e.get('issue')) for e in exercises)}}
    if not tx.get('collection_analysis_jobs',jid):
        path,file_sha=tx.add_blob(json.dumps(payload.model_dump(),ensure_ascii=False,indent=2).encode('utf8'),
            layout.for_subject(tx,subject_id,layout.SUBJECT_KNOWLEDGE),f'codex-source-map-{identity[:16]}.json','application/json')
        data['source_import_file']={'file_path':path,'sha256':file_sha}
        tx.insert('collection_analysis_jobs',{'id':jid,'collection_id':version['collection_id'],'version_id':version['id'],'subject_id':subject_id,
            'status':'needs_review' if flags else 'ready','stage':'Codex source review saved; pending pages remain excluded' if pending_pages else 'Codex source map imported without API generation','provider':'codex','model':'Codex source review',
            'analysis_version':VERSION,'max_cost_micros':0,'done':checked_units if pending_pages else len(plan['steps']),'total':len(plan['steps']),'plan':plan,'map_id':mid})
        tx.insert('subject_maps',{'id':mid,'collection_id':version['collection_id'],'version_id':version['id'],'job_id':jid,'data':data})
    saved=tx.get('subject_maps',mid)
    return {'map_id':mid,'job_id':jid,'ai_generation':False,'coverage':data['coverage'],
        'source_file':saved['data'].get('source_import_file')}
