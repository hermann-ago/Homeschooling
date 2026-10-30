"""Editable, versioned source-analysis instructions; no learner-specific content."""
from pathlib import Path
import hashlib

from storage.store import RevisionConflict
from storage.layout import MATERIAL_SKILLS

KINDS = {'book-json': ('Livro em JSON', 'Transcrição, imagens e estrutura das páginas'),
         'material-links': ('Relações entre materiais', 'Leituras, exercícios, pré-requisitos e gabaritos'),
         'script-review': ('Revisão do roteiro', 'Clareza, ritmo, fontes e interações antes do áudio')}


def packet(ctx, key):
    if key not in KINDS:
        raise ValueError('Choose an available material skill')
    from services.ai_provider import _generation_scope
    scope = _generation_scope.get()
    db = getattr(ctx,'store',None)
    job = db.get('collection_analysis_jobs', scope) if scope and db else None
    frozen = (job or {}).get('plan', {}).get('material_skills', {}).get(key)
    if frozen:
        return frozen
    rows = db.find('material_skills', key=key) if db else []
    current = max(rows, key=lambda r:r['version'], default=None)
    if current:
        result={k:current[k] for k in ('key','version','content','sha256','file_path','created_at')}
        stamp=result['created_at']
        result['created_at']=stamp.isoformat() if hasattr(stamp,'isoformat') else stamp
        return result
    path = Path(__file__).resolve().parents[2] / 'tutor/materials' / key / 'GUIDE.md'
    content = path.read_text(encoding='utf-8')
    return {'key':key, 'version':0, 'content':content, 'sha256':hashlib.sha256(content.encode()).hexdigest(), 'file_path':str(path), 'created_at':None}


def inventory(ctx):
    return [{'title': title, 'description': description, **packet(ctx,key),
             'history':sorted(ctx.store.find('material_skills',key=key),key=lambda r:r['version'],reverse=True)}
            for key,(title,description) in KINDS.items()]


def save(ctx, tx, key, content, expected_version):
    current = packet(ctx,key)
    if current['version'] != expected_version:
        raise RevisionConflict('This material skill changed. Reload before saving.', current)
    content=content.strip()
    if not 1 <= len(content) <= 30000:
        raise ValueError('Instructions must contain 1–30,000 characters')
    if content == current['content'].strip():
        return current
    if not tx.find('material_skills',key=key):
        baseline_path,_=tx.add_blob(current['content'].encode('utf-8'),MATERIAL_SKILLS,f'{key}-GUIDE-v0.md','text/markdown')
        tx.insert('material_skills',{'key':key,'version':0,'content':current['content'],'sha256':current['sha256'],'file_path':baseline_path})
    version=current['version']+1
    path,_=tx.add_blob(content.encode('utf-8'),MATERIAL_SKILLS,f'{key}-GUIDE-v{version}.md','text/markdown')
    row=tx.insert('material_skills',{'key':key,'version':version,'content':content,
        'sha256':hashlib.sha256(content.encode()).hexdigest(),'file_path':path})
    return row


def ensure(ctx):
    """Preserve the shipped baseline once, alongside future family edits."""
    from storage import FileUnavailable
    for key in KINDS:
        if ctx.store.find('material_skills',key=key):
            continue
        item=packet(ctx,key)
        with ctx.store.transaction(kind='material_skills.seed',summary='Preserved initial material-analysis instructions') as tx:
            path=None
            try:
                path,_=tx.add_blob(item['content'].encode('utf-8'),MATERIAL_SKILLS,f'{key}-GUIDE-v0.md','text/markdown')
            except FileUnavailable:
                pass
            tx.insert('material_skills',{'key':key,'version':0,'content':item['content'],'sha256':item['sha256'],'file_path':path})
