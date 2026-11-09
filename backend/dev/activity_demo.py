"""Offline browser rehearsal with invented records and disposable storage.

Run with the existing backend development environment after building frontend.
This process never opens the family's database, books, keys or spending ledger.
"""
from __future__ import annotations

import argparse
import copy
import os
import sys
import tempfile
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
os.environ["HOMESCHOOLING_SKIP_APP"] = "1"
os.environ["OPENAI_API_KEY"] = ""
os.environ["GEMINI_API_KEY"] = ""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--recorded-voice", action="store_true", help="Use synthetic WAV recordings through a mocked provider")
    parser.add_argument("--aligned-voice", action="store_true", help="Rehearse aligned playback with synthetic audio/timings and no provider calls")
    parser.add_argument("--answer-controls", action="store_true", help="Rehearse true/false, one choice and select-all with invented records")
    parser.add_argument('--practice-sections',action='store_true',help='Rehearse grouped items, typed spelling and matching without family records')
    parser.add_argument('--paced-book-work', action='store_true', help="Rehearse a subject whose book work is done in the book, with an offline end-of-lesson photo check")
    parser.add_argument('--teaching-script',action='store_true',help='Prepare an offline natural teaching script through the application compiler')
    args = parser.parse_args()
    import uvicorn
    from tests.conftest import Harness
    from tests.test_tutoring import seed_history
    from tutoring import guide, interactive, passages, skills

    with tempfile.TemporaryDirectory(prefix="homeschooling-activity-rehearsal-") as folder:
        harness = Harness(Path(folder))
        ctx = harness.ctx
        seeded = seed_history(harness)
        with ctx.store.transaction() as tx:
            tx.update("children", seeded["lucas"]["id"], {"name": "Practice learner"})
            tx.delete("checkpoints", "2026-09-24-genghis-cp")
            tx.update("tutor_sessions", "2026-09-24-genghis", {"status": "completed"})
        topic = ctx.store.get("topics", seeded["genghis"]["id"])
        passage = passages.load(ctx, topic)
        plan = {"mode": "expand", "segments": [
            {"type": "intro", "text": "Welcome, Practice learner. Today we will read about people joining together. Keep your book beside you."},
            {"type": "read", "from": 0, "to": len(passage["sentences"]) - 1},
            {"type": "action", "text": "What did Genghis Khan do with the tribes?", "action_kind": "answer"},
            {"type": "recap", "text": "We read about the tribes and explained how they joined together. Your own answers and any help stay saved separately."},
        ]}
        if args.answer_controls:
            plan['segments'][2:3] = [
                {'type':'activity','activity_kind':'ask_question','content':{
                    'prompt':'True or false: Genghis Khan united the tribes.', 'answer_format':'true_false',
                    'response_modes':['choice','text']}},
                {'type':'activity','activity_kind':'ask_question','content':{
                    'prompt':'What did Genghis Khan do with the tribes?', 'answer_format':'single_choice',
                    'choices':[{'id':'a','label':'A. He united the tribes.'},{'id':'b','label':'B. He left them separate.'}],
                    'response_modes':['choice','text']}},
                {'type':'activity','activity_kind':'ask_question','content':{
                    'prompt':'Select all the statements from the reading.', 'answer_format':'multiple_select',
                    'choices':[{'id':'a','label':'The Mongols came from the north.'},{'id':'b','label':'Genghis Khan united the tribes.'},
                               {'id':'c','label':'The tribes stayed separate.'}], 'response_modes':['choice','text']}},
            ]
        if args.practice_sections:
            refs=[{'document_id':topic['document_id'],'page':2}]
            plan['segments'][2:3]=[
                {'type':'activity','activity_kind':'ask_question','origin':'required_book','source_refs':refs,
                 'content':{'prompt':prompt,'answer_format':'true_false','response_modes':['choice','text']}}
                for prompt in ('True or false: Genghis Khan united the tribes.','True or false: the tribes stayed separate.')]
            plan['segments'][4:4]=[
                {'type':'activity','activity_kind':'ask_question','origin':'required_book','source_refs':refs,
                 'content':{'prompt':'Type the word '+word+'.','evidence_requirement':'spelling','response_modes':['text']}}
                for word in ('moon','sun')]
            plan['segments'][6:6]=[{'type':'activity','activity_kind':'ask_question','content':{
                'prompt':'Match each animal to its habitat.','matching':{
                    'items':[{'id':'bird','label':'Bird'},{'id':'fish','label':'Fish'}],
                    'options':[{'id':'water','label':'Water'},{'id':'air','label':'Air'}]}}}]
        if args.paced_book_work:
            with ctx.store.transaction() as tx:
                tx.update("subjects", seeded["history"]["id"], {"book_work": "paced"})
        subject = ctx.store.get("subjects", seeded["history"]["id"])
        if not args.teaching_script:
            with ctx.store.transaction() as tx:
                guide.save(tx, topic, passage, guide.build(passage["sentences"], plan), model="offline synthetic tutor",
                    language="en-US", skill=skills.packet(ctx.store, subject))

        def assess(*_args, **_kwargs):
            # The same rehearsal can enter the app's real Test Mode UI. Read
            # its request-selected copy, never the outer synthetic base store.
            from dependencies import context
            active_ctx = context()
            messages = sorted((m for m in active_ctx.store.all("lesson_dialogue") if m["role"] == "student"),
                              key=lambda row: (row["created_at"], row["sequence"] or 0))
            answer = messages[-1]["text"].casefold() if messages else ""
            action = active_ctx.store.get("lesson_actions", f"{messages[-1]['session_id']}:{messages[-1]['action_id']}") if messages else None
            if args.practice_sections and action:
                prompt=action['prompt'].casefold()
                correct=('stayed separate' in prompt and answer=='false' or 'united the tribes' in prompt and answer=='true'
                    or 'type the word moon' in prompt and answer=='moon' or 'type the word sun' in prompt and answer=='sun'
                    or 'match each animal' in prompt and answer=='bird → air\nfish → water')
                return {'feedback':'Yes. Your answer matches the task.' if correct else 'Look at the current item and try once more.',
                    'result':'Correct' if correct else 'Not yet','ready_to_continue':bool(correct)}
            if action and action["kind"] == "question":
                return {"feedback": "A tribe is a community of people. Look again at what happened when the communities joined.",
                        "result": "Unanswered", "ready_to_continue": True}
            if "united" in answer or "together" in answer:
                return {"feedback": "Yes. He united the tribes. You explained the change.", "result": "Correct", "ready_to_continue": True}
            if args.answer_controls and answer.split('\n',1)[0].strip() == 'true':
                return {'feedback':'Yes. That statement matches the reading.', 'result':'Correct','ready_to_continue':True}
            return {"feedback": "Look again at the sentence about the tribes.", "result": "Not yet",
                    "follow_up": "What changed for the tribes?", "ready_to_continue": False}

        def generated(_prompt, *, schema=None, **_kwargs):
            from tutoring.script_review import Review
            if args.practice_sections and schema and schema.__name__ in ('TranscribedPageExact', 'WorkbookAssessmentExact'):
                from dependencies import context
                from tutoring import page_work
                active_ctx = context()
                job = max((j for j in active_ctx.store.all('activity_jobs') if j['kind'] == 'page_work'), key=lambda j: j['updated_at'])
                actions = job['input_snapshot']['actions']
                if schema.__name__ == 'TranscribedPageExact':
                    texts = ['True', 'False', 'moon', 'sun']
                    return schema.model_validate({'items': [{'item_id': a['action_id'], 'text': texts[i], 'uncertain': False} for i, a in enumerate(actions)]}).model_dump()
                return schema.model_validate({'feedback': 'Your page is checked.', 'items': [
                    {'item_id': r['item_id'], 'result': 'Correct', 'feedback': 'Your answer matches this book task.', 'ready_to_continue': True}
                    for r in job['input_snapshot']['confirmed']]}).model_dump()
            if args.paced_book_work and schema and schema.__name__ == 'BookCheckReplyExact':
                from dependencies import context
                job = max((j for j in context().store.all('activity_jobs') if j['kind'] == 'book_check'), key=lambda j: j['updated_at'])
                tasks = job['input_snapshot']['tasks']
                return schema.model_validate({'summary': 'Offline check: one answer to look at again.', 'items': [
                    {'item_id': t['item_id'], 'answer': 'True' if i else 'He fought them', 'result': 'looks_right' if i else 'check_again',
                     'note': '' if i else 'Look again at what happened to the tribes.'} for i, t in enumerate(tasks)]}).model_dump()
            if schema and issubclass(schema,Review):return {'findings':[]}
            if schema and schema.__name__ == "HintReply":
                if "Show a short worked analogy" in _prompt:
                    return {"text": "Imagine two separate school clubs. They agree to become one team. First there were two groups; afterward there was one. This is an imaginary example."}
                if "Explain the current idea differently" in _prompt:
                    return {"text": "Separate groups can decide to act as one group. Think about what changed between the groups at the beginning and at the end of your reading."}
                return {"text": "Think about joining separate groups into one."}
            if schema and schema.__name__ == "TranscriptionReply":
                return {"text": "The tribes joined together.", "uncertain": False}
            raise ValueError("This offline rehearsal does not call a paid provider.")

        ctx.ai.generate = generated
        if args.recorded_voice or args.aligned_voice:
            import base64
            import io
            import wave
            import httpx
            from tests.test_ai_costs import enable_voice
            def recorded(_request):
                stream = io.BytesIO()
                with wave.open(stream, 'wb') as wav:
                    wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(16000)
                    wav.writeframes(b'\0\0' * 16000 * 12)
                return httpx.Response(200, json={'status': 'completed', 'usage': {'total_input_tokens': 100, 'total_output_tokens': 25},
                    'output_audio': {'mime_type': 'audio/wav', 'data': base64.b64encode(stream.getvalue()).decode()}})
            enable_voice(harness, recorded)
            if args.aligned_voice:
                from tutoring import narration_alignment
                ctx.config.update(tts={**ctx.config.get('tts'), 'aligned_blocks': True})
                # Only this disposable rehearsal bypasses acoustic inference.
                # Real-model alignment is verified separately against saved speech.
                narration_alignment.available = lambda *_: True
                narration_alignment.validate_script = lambda *_: None
                narration_alignment.align = lambda _ctx, _data, rows, _language: {
                    'sentenceStarts': [12*i/len(rows) for i in range(len(rows))],
                    'duration': 12., 'alignment': {'version': narration_alignment.VERSION}}
        if args.teaching_script:
            from tutoring.teaching_script import TeachingScript
            # Exercise the ordinary preview/cap UI; all writing/review calls
            # below are mocked and this disposable host has no provider keys.
            ctx.config.update(ai={**ctx.config.get('ai',{}),'monthly_generation_enabled':True})
            authored={'welcome':'Imagine several groups deciding to become one team. Let us discover what happened to the tribes in our reading.',
                'turns':[{'type':'read','first':0,'last':len(passage['sentences'])-1},
                    {'type':'ask','purpose':'discussion','prompt':'What changed for the tribes when Genghis Khan united them?'}],
                'closing':'We followed how separate tribes came together. You can revisit the reading whenever you want.'}
            def scripted(_prompt,_models,**kwargs):
                assert issubclass(kwargs['schema'],TeachingScript)
                return kwargs['schema'].model_validate(authored).model_dump(),'offline synthetic writer'
            guide.write_plan=scripted
        else:
            guide.write_plan = lambda *_args, **_kwargs: (copy.deepcopy(plan), "offline synthetic tutor")
        interactive.gemini_turn = assess
        print(f"SYNTHETIC ONLY · http://127.0.0.1:{args.port}/lesson?learner={seeded['lucas']['id']}&topic={topic['id']}", flush=True)
        print(f"Disposable records: {folder}", flush=True)
        uvicorn.run(harness.app, host="127.0.0.1", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
