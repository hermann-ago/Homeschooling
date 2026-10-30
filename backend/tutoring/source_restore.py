"""Restore missing legacy PDFs with checked locators while retaining learner IDs."""
import hashlib,io
from pydantic import BaseModel,ConfigDict,Field
from pypdf import PdfReader
from storage.store import RevisionConflict
from .books import norm


class Locator(BaseModel):
    model_config=ConfigDict(extra='forbid')
    topic_id:int=Field(ge=1)
    expected_revision:int=Field(ge=1)
    page_start:int=Field(ge=1)
    page_end:int=Field(ge=1)
    pdf_page_offset:int
    source_quote:str=Field(min_length=12,max_length=500)


class NewSourceTopic(BaseModel):
    model_config=ConfigDict(extra='forbid')
    title:str=Field(min_length=1,max_length=200)
    chapter_order:int=Field(ge=0)
    page_start:int=Field(ge=1)
    page_end:int=Field(ge=1)
    pdf_page_offset:int
    source_quote:str=Field(min_length=12,max_length=500)


class RestoreSource(BaseModel):
    model_config=ConfigDict(extra='forbid')
    path:str=Field(min_length=1,max_length=1000)
    sha256:str=Field(pattern=r'^[0-9a-f]{64}$')
    expected_revision:int=Field(ge=1)
    note:str=Field(min_length=10,max_length=2000)
    topics:list[Locator]=Field(min_length=1,max_length=2000)
    additional_topics:list[NewSourceTopic]=Field(default_factory=list,max_length=500)


def inspect(ctx,subject_id,document_id,payload):
    doc=ctx.store.get('documents',document_id)
    topics=ctx.store.find('topics',subject_id=subject_id,document_id=document_id)
    if not doc or not topics:raise ValueError('Choose an existing book in this subject')
    if any(t['subject_id']!=subject_id for t in ctx.store.find('topics',document_id=document_id)):
        raise ValueError('This legacy book is shared; restore each source binding before replacing it')
    if doc.get('sha256') and doc['sha256']!=payload.sha256:
        raise ValueError('This is a different edition; keep it as a separate source rather than rewriting historical source identity')
    resolved=ctx.files.resolve(payload.path)
    if resolved.stat().st_size>262144000:raise ValueError('Choose an original PDF smaller than 250 MiB')
    data=ctx.files.read(payload.path)
    if hashlib.sha256(data).hexdigest()!=payload.sha256 or not data.startswith(b'%PDF'):
        raise ValueError('The selected original PDF does not match the source checksum')
    try:
        import pymupdf
        reader=pymupdf.open(stream=data,filetype='pdf')
        count=len(reader)
        text=lambda n:reader[n-1].get_text('text',sort=True)
    except ImportError:
        reader=PdfReader(io.BytesIO(data));count=len(reader.pages)
        text=lambda n:reader.pages[n-1].extract_text() or ''
    for item in [*payload.topics,*payload.additional_topics]:
        first=item.page_start+item.pdf_page_offset;last=item.page_end+item.pdf_page_offset
        if item.page_end<item.page_start or not 1<=first<=last<=count:
            raise ValueError('A lesson range is outside the original PDF')
        if norm(item.source_quote) not in norm(text(first)):
            raise ValueError(f'A source locator needs its literal opening-page quote: {first}')
    return {'file_path':ctx.files.relative(resolved),'sha256':payload.sha256,'size_bytes':len(data),
        'page_count':count,'original_filename':resolved.name,'source':'drive','status':'ready'}


def save(ctx,tx,subject_id,document_id,payload,verified):
    doc=tx.get('documents',document_id)
    if not doc or doc['revision']!=payload.expected_revision:
        raise RevisionConflict('This book changed; reopen the restoration preview',doc)
    topics=tx.find('topics',subject_id=subject_id,document_id=document_id)
    rows={t.topic_id:t for t in payload.topics}
    if len(rows)!=len(payload.topics) or set(rows)!={t['id'] for t in topics}:
        raise ValueError('Include every existing lesson in this exact book, once')
    for t in topics:
        if rows[t['id']].expected_revision!=t['revision']:
            raise RevisionConflict('A lesson changed during source restoration',t)
    orders={t['chapter_order'] for t in topics}
    if any(n.chapter_order in orders for n in payload.additional_topics) or len({n.chapter_order for n in payload.additional_topics})!=len(payload.additional_topics):
        raise ValueError('Additional source lessons need distinct positions after the existing index')
    before={'document':doc,'topics':[{k:t[k] for k in ('id','title','page_start','page_end','pdf_page_offset','pdf_filename','chapter_order','completed','completed_at')} for t in topics]}
    tx.update('documents',document_id,verified,expected_revision=payload.expected_revision)
    for t in topics:
        loc=rows[t['id']]
        tx.update('topics',t['id'],{'page_start':loc.page_start,'page_end':loc.page_end,
            'pdf_page_offset':loc.pdf_page_offset,'pdf_filename':verified['original_filename']})
    core=any(t['is_core'] for t in topics)
    for item in payload.additional_topics:
        tx.insert('topics',{'subject_id':subject_id,'document_id':document_id,'title':item.title,
            'chapter_order':item.chapter_order,'page_start':item.page_start,'page_end':item.page_end,
            'pdf_page_offset':item.pdf_page_offset,'pdf_filename':verified['original_filename'],
            'is_core':core,'language':'en','source_key':f'restored-document-{document_id}:{item.chapter_order}'})
    import json
    history=tx.insert('document_restorations',{'document_id':document_id,'subject_id':subject_id,
        'before':json.loads(json.dumps(before,default=str)),'after':{'document':verified,'locators':[t.model_dump() for t in payload.topics],
        'additional_topics':[t.model_dump() for t in payload.additional_topics]},'note':payload.note})
    return {'document_id':document_id,'restoration_id':history['id'],'preserved_lessons':len(topics),
        'additional_source_lessons':len(payload.additional_topics),'ai_generation':False}
