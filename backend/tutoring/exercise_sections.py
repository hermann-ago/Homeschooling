"""Read-only exercise grouping over canonical activities; never a second queue."""
import hashlib


def sections(actions):
    """Only contiguous required items of the same format and exact source group.

    Uses source locators, not generated titles or prompt similarity. Metadata
    contains counts, never unreached questions, choices or private answer keys.
    """
    groups=[]; current=[]; previous=None
    for action in actions:
        if action.get('parent_activity_id'):continue
        content=action.get('activity_content') or {}
        refs=[*(action.get('source_refs') or []),*(content.get('source_refs') or [])]
        locations=tuple(sorted({(r['document_id'],r['page']) for r in refs if r.get('document_id') and r.get('page')}))
        family='spelling' if content.get('evidence_requirement')=='spelling' else content.get('answer_format')
        eligible=(action.get('origin')=='required_book' and not action.get('parent_activity_id')
                  and action.get('activity_kind') in ('ask_question','request_book_work')
                  and family in ('spelling','true_false','single_choice','multiple_select') and locations)
        signature=(action['session_id'],locations,family) if eligible else None
        if current and (signature is None or signature!=previous):groups.append(current);current=[]
        if signature is not None:current.append(action)
        previous=signature
    if current:groups.append(current)
    labels={'spelling':'Spelling practice','true_false':'True or false','single_choice':'Choose an answer','multiple_select':'Select the answers'}
    result={}
    for group in groups:
        if len(group)<2:continue
        family='spelling' if (group[0].get('activity_content') or {}).get('evidence_requirement')=='spelling' else group[0]['activity_content']['answer_format']
        identity='practice-'+hashlib.sha256('|'.join(a['id'] for a in group).encode()).hexdigest()[:20]
        completed=sum(a['status']=='answered' for a in group)
        for index,action in enumerate(group,1):
            result[action['action_id']]={'id':identity,'kind':family,'title':labels[family],
                'item':index,'total':len(group),'completed':completed}
    return result
