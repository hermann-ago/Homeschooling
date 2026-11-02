"""Preparation units are source evidence, not compulsory extra learner clicks."""
import copy
import pytest

from tutoring import guide,lesson_quality
from tutoring.answer_controls import binary_subitems,book_controls


def test_checked_title_story_and_attribution_are_one_turn_with_all_provenance():
    source=[{'text':x} for x in ('An invented fable.','A wren helped a bear.','An invented author.')]
    readings=[{'id':f'r{i}','document_id':4,'page':1+i//2,'text':s['text'],'from':i,'to':i}
              for i,s in enumerate(source)]
    manifest={'readings':readings,'tasks':[],'checked_pages':[1,2]}
    plan={'mode':'tidy','segments':[{'type':'intro','text':'Let us listen.'},
        *[{'type':'read','from':r['from'],'to':r['to'],'source_block_id':r['id']} for r in readings],
        {'type':'action','text':'Who helped whom?','action_kind':'answer'}]}
    resolved=lesson_quality.resolve_readings(plan,manifest);original=copy.deepcopy(resolved)
    compiled=lesson_quality.coherent_readings(resolved)
    assert resolved==original
    assert compiled['segments'][1]['source_block_ids']==['r0','r1','r2']
    assert [r['page'] for r in compiled['segments'][1]['source_refs']]==[1,1,2]
    built=guide.build(source,compiled)
    assert len(built['activities'])==3 and built['activities'][-1]['content']['prompt']=='Who helped whom?'
    assert lesson_quality.validate(built,manifest)['readings_preserved']==3
    # A saved guide is never silently regrouped when it is loaded again.
    old=guide.build(source,resolved)
    assert len(guide.guide_activities(old))==5
    overlapping=copy.deepcopy(resolved)
    overlapping['segments'][2]['from']=0
    assert len(lesson_quality.coherent_readings(overlapping)['segments'])==3


def test_reading_compilation_never_crosses_work_or_unchecked_gaps():
    plan={'segments':[{'type':'read','from':0,'to':0,'text':'One.','source_block_id':'r1'},
        {'type':'read','from':2,'to':2,'text':'Three.','source_block_id':'r3'},
        {'type':'action','text':'Your turn.','action_kind':'answer'},
        {'type':'read','from':3,'to':3,'text':'Four.','source_block_id':'r4'},
        {'type':'read','from':4,'to':4,'text':'Unverified.'}]}
    assert lesson_quality.coherent_readings(plan)==plan


def test_checked_typography_uses_exact_transcription_without_inventing_words():
    original='A\no tiny bird fi nally learned the mean-\ning.'
    correct='Ao tiny bird finally learned the meaning.'
    page={'elements':[{'kind':'text','text':correct}]}
    assert lesson_quality.checked_reading_text(original,page)==correct
    assert lesson_quality.checked_reading_text(original,{'elements':[{'kind':'text','text':correct.replace('bird','bear')}]})==original
    assert lesson_quality.checked_reading_text('A well-known bird.',{'elements':[{'kind':'text','text':'A wellknown bird.'}]})=='A well-known bird.'


def test_binary_statement_list_keeps_each_item_and_its_original_instruction():
    task={'id':'checked-list','pages':[13],'reference':'Reading','prompt':
        'Decida se é verdadeira ou falsa:\nA small bird helped.\nThe bear flew.'}
    parts=binary_subitems(task)
    assert [p['id'] for p in parts]==['checked-list:statement-1','checked-list:statement-2']
    assert all(p['prompt'].startswith('Decida se é verdadeira ou falsa:\n') for p in parts)
    assert parts[1]['prompt'].endswith('The bear flew.')
    assert book_controls(parts[0])['choices']==[{'id':'true','label':'Verdadeiro'},{'id':'false','label':'Falso'}]
    assert book_controls(task)=={}  # never one binary selector for a whole list
    ambiguous={**task,'prompt':'True or false:\nA bird with a\nvery long name helped.'}
    assert binary_subitems(ambiguous)==[ambiguous]


def test_preparation_context_supplies_family_and_source_contract_once():
    text=guide.prompt({'title':'A fable','sentences':[{'text':'A bird helped.'}]},subject='Literacy',
        learner='Practice learner',grade='3',language='en-US',learner_context={
            'family_tutoring':{'content':'UNIQUE-FAMILY-STYLE','learner_profile':{}},
            'source_requirements':{'readings':[{'id':'story','from':0,'to':0}],'tasks':[]}})
    assert text.count('UNIQUE-FAMILY-STYLE')==1
    assert 'source_block_id' in text and 'source_requirements' not in text




