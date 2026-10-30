"""Local revalidation of source corrections and explicit source-map decisions.

No AI call, learner write, teaching selection or mutation of an earlier map.
"""
import copy
from pydantic import BaseModel, ConfigDict, Field
from typing import Literal

from storage.store import sha256_text
from . import books
from .collections import binding
from .subject_analysis import safe_pages, valid_quote, ReadingQuote


class LinkDecision(BaseModel):
    model_config=ConfigDict(extra='forbid')
    exercise_id:str=Field(min_length=1,max_length=180)
    status:Literal['proposed','not_required','needs_review']
    evidence:list[ReadingQuote]=Field(default_factory=list,max_length=5)
    instruction_quote:str=Field(default='',max_length=1000)
    reason:str=Field(min_length=1,max_length=650)


class MaterialReview(BaseModel):
    model_config=ConfigDict(extra='forbid')
    expected_map_id:str
    expected_version_id:str
    expected_source_hashes:dict[str,str]
    note:str=Field(min_length=1,max_length=2000)
    decisions:list[LinkDecision]=Field(default_factory=list,max_length=10000)


def apply(ctx,tx,subject_id,payload):
    linked=binding(tx,subject_id)
    row=tx.get('subject_maps',payload.expected_map_id)
    collection=tx.get('book_collections',linked['collection_id']) if linked else None
    if not row or not collection or row['collection_id']!=collection['id'] or row['version_id']!=collection['active_version'] or payload.expected_version_id!=row['version_id']:
        raise ValueError('The collection or saved map changed; reopen before reviewing sources')
    jobs=tx.find('collection_analysis_jobs',collection_id=collection['id'])
    if any(j['status'] in ('queued','running') for j in jobs):
        raise ValueError('Wait for the current source analysis to finish before applying corrections')
    job=tx.get('collection_analysis_jobs',row['job_id'])
    if not job or job['map_id']!=row['id']:
        raise ValueError('The saved map changed; reopen the latest overview before reviewing sources')
    if job['status'] not in ('ready','needs_review') or not row['data']['coverage']['complete']:
        raise ValueError('Finish the source map before applying reviewed source corrections')
    data=copy.deepcopy(row['data']);sources=data['books'];scans={};read_units={};review_ids={};current_hashes={}
    for src in sources:
        companions=tx.find('book_companions',sha256=src['sha256'],role=src['role'])
        if companions:current_hashes[str(src['document_id'])]=companions[0]['content_sha256']
        history=tx.find('book_source_reviews',sha256=src['sha256'],role=src['role'])
        review_ids[src['id']]=max(history,key=lambda r:r['version'])['id'] if history else None
        scans[src['id']]=[]
        for first in range(1,src['pages']+1,books.UNIT_PAGES):
            step={'source_id':src['id'],'first':first,'last':min(first+books.UNIT_PAGES-1,src['pages'])}
            unit=ctx.subject_analysis.cached_scan(src,step)
            if not unit:raise ValueError('A saved source scan is missing; no paid rescan was requested')
            scans[src['id']].append((step,unit['data']))
    if current_hashes!=payload.expected_source_hashes:
        raise ValueError('Book JSON files changed; reload the sources before saving this review')
    issues=[]
    for section in data['sections']:
        src=next(s for s in sources if s['id']==section['source_id'])
        first,last=section['pages']
        scan=next(value for step,value in scans[src['id']] if step['first']==first)
        pages=safe_pages(src,scan)
        read_units[section['id']]={'pages':pages}
        # Existing concepts remain proposals. Only typographic quote repair is
        # automatic; it never invents a new explanation or dependency.
        for concept in section['concepts']:
            for cite in concept['evidence']:
                actual=books.original_quote(pages.get(cite['page'],''),cite['quote'])
                if actual:cite['quote']=actual
            if not all(valid_quote(q,pages) for q in concept['evidence']):
                concept['status']='needs_review';issues.append(f"Concept '{concept['title']}' still needs source evidence")
        section['issues']=[f"PDF page {p['page']}: {p['issue']}" for p in scan['pages'] if p.get('issue')]
        issues.extend(section['issues'])
    concepts={c['id']:c for s in data['sections'] for c in s['concepts']}
    data['concepts']=[copy.deepcopy(concepts.get(c['id'],c)) for c in data['concepts']]
    exercises,private=ctx.subject_analysis.exercises(job,scans,sources)
    oldlinks={l['exercise_id']:l for l in data['exercise_links']}
    supplied={d.exercise_id:d for d in payload.decisions}
    if len(supplied)!=len(payload.decisions) or set(supplied)-{e['id'] for e in exercises}:
        raise ValueError('Each review decision must identify one exercise in this exact source snapshot')
    links=[]
    for exercise in exercises:
        eid=exercise['id'];decision=supplied.get(eid)
        link=copy.deepcopy(oldlinks.get(eid,{'exercise_id':eid,'status':'needs_review','evidence':[],'reason':'Original task source is saved; its pedagogical relationship needs review'}))
        if decision:
            link={'exercise_id':eid,'status':decision.status,'evidence':[q.model_dump() for q in decision.evidence],
                'reason':decision.reason,'review_method':'source_review'}
            if decision.status=='not_required':
                if not exercise['student_safe'] or len(books.norm(decision.instruction_quote))<12 or not books.original_quote(exercise['prompt'],decision.instruction_quote):
                    raise ValueError('Self-contained work needs a literal quote from its original task instructions')
                link['source_instruction_quote']=decision.instruction_quote
        for cite in link.get('evidence',[]):
            pages=read_units.get(cite['unit_id'],{}).get('pages',{})
            actual=books.original_quote(pages.get(cite['page'],''),cite['quote'])
            if actual:cite['quote']=actual
        supported=bool(link.get('evidence')) and all(valid_quote(q,read_units.get(q['unit_id'],{}).get('pages',{})) for q in link['evidence'])
        if link['status'] in ('proposed','preserved') and not supported:
            if decision:raise ValueError('A proposed relationship must cite the exact checked reading page')
            link.update(status='needs_review',evidence=[],reason='The earlier reading quotation is not supported by the corrected source')
        links.append(link)
    data.update(exercises=exercises,private_answers=private,exercise_links=links,issues=list(dict.fromkeys(issues)),
        source_review_ids=review_ids,source_companion_hashes=current_hashes,supersedes_map_id=row['id'],
        source_review_note=payload.note,prior_analysis_issues=data.get('issues',[]))
    from .material_skills import packet
    data['material_skills']={key:packet(ctx,key) for key in ('book-json','material-links')}
    data['flagged_items']=len(data['issues'])+sum(l['status']=='needs_review' for l in links)+sum(e['answer_link_status']=='needs_review' for e in exercises)
    data['coverage']={**data['coverage'],'exercises':len(exercises),'complete':True,'pending_exercises':0}
    mid='subject-map-'+sha256_text([row['id'],current_hashes,[d.model_dump() for d in payload.decisions],payload.note])[:32]
    if not tx.get('subject_maps',mid):
        tx.insert('subject_maps',{'id':mid,'collection_id':row['collection_id'],'version_id':row['version_id'],'job_id':row['job_id'],'data':data})
    tx.update('collection_analysis_jobs',row['job_id'],{'map_id':mid,'status':'needs_review' if data['flagged_items'] else 'ready',
        'stage':'Source corrections saved without AI generation','error':None})
    return mid
