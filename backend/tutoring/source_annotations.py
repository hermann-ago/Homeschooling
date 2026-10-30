"""Versioned edition/page-bound teaching notes, shared across learners and subjects.

Assessment exceptions are teacher-only. Notes never rewrite original book text,
answer keys, immutable attempts or a running session's frozen context.
"""
import json
from urllib.parse import urlparse
from pydantic import BaseModel, ConfigDict, Field, model_validator
from storage.store import RevisionConflict, sha256_text
from storage import layout


class Annotation(BaseModel):
    model_config = ConfigDict(extra='forbid')
    document_id: int
    expected_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')
    expected_version: int = Field(ge=0)
    first_page: int = Field(ge=1)
    last_page: int = Field(ge=1)
    title: str = Field(min_length=1, max_length=180)
    teaching_note: str = Field(default='', max_length=8000)
    assessment_note: str = Field(default='', max_length=4000)
    references: list[str] = Field(default_factory=list, max_length=12)
    active: bool = True

    @model_validator(mode='after')
    def bounds(self):
        if self.last_page < self.first_page or not self.title.strip():
            raise ValueError('Choose a title and an ordered PDF page range')
        for url in self.references:
            if len(url)>1500 or urlparse(url).scheme not in ('http','https') or not urlparse(url).netloc:
                raise ValueError('Source references must be complete HTTP or HTTPS links')
        return self


def documents(db, subject_id):
    ids={t['document_id'] for t in db.find('topics',subject_id=subject_id) if t.get('document_id')}
    ids.update(b['document_id'] for b in db.find('subject_books',subject_id=subject_id) if not b['archived'])
    return [d for identity in sorted(ids) if (d:=db.get('documents',identity))]


def latest(db):
    result={}
    for row in db.all('source_annotations'):
        if row['version']>result.get(row['key'],{}).get('version',0):result[row['key']]=row
    return list(result.values())


def save(tx, subject_id, payload):
    doc=next((d for d in documents(tx,subject_id) if d['id']==payload.document_id),None)
    if not doc or doc['sha256']!=payload.expected_sha256:
        raise ValueError('Choose the current book edition from this subject')
    if payload.last_page>doc['page_count']:raise ValueError('The note extends beyond this PDF')
    key=sha256_text([doc['sha256'],payload.first_page,payload.last_page,payload.title.strip()])
    prior=next((r for r in latest(tx) if r['key']==key),None)
    if payload.expected_version!=(prior['version'] if prior else 0):
        raise RevisionConflict('This source note changed. Reload before saving.',prior)
    body=payload.model_dump(exclude={'document_id','expected_sha256','expected_version'})
    body.update(key=key,document_sha256=doc['sha256'],version=payload.expected_version+1)
    path,_=tx.add_blob(json.dumps(body,ensure_ascii=False,indent=2).encode(),
        layout.for_subject(tx,subject_id,layout.TEACHING_SKILL),f'source-note-{key[:16]}-v{body["version"]}.json','application/json')
    return tx.insert('source_annotations',{'id':f'{key}-v{body["version"]}',**body,'file_path':path})


def packet(db, topic, *, assessment=False):
    from .passages import pdf_range
    doc=db.get('documents',topic.get('document_id'))
    if not doc:return []
    first,last=pdf_range(topic)
    fields=['id','version','document_sha256','first_page','last_page','title','teaching_note','references']
    if assessment:fields.append('assessment_note')
    return [{k:r.get(k) for k in fields} for r in sorted(latest(db),key=lambda r:r['key'])
        if r['active'] and r['document_sha256']==doc['sha256'] and r['first_page']<=last and r['last_page']>=first]
