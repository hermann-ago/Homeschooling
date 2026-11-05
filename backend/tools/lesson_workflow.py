"""Export, validate and publish Codex-authored lessons through the normal app pipeline.

No lesson-writing or review API calls. Voice is a separate, explicit operation.
Run with backend/venv/Scripts/python.exe backend/tools/lesson_workflow.py --help.
"""
import argparse
import base64
import hashlib
import json
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def save(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


def validate(packet, script):
    from tutoring import book_questions, guide, lesson_quality, page_script
    script = page_script.schema(packet['package'], packet['context'], packet['language']).model_validate(script).model_dump()
    plan = page_script.compile_script(script, packet['package'], packet['context'], packet['language'])
    # Compilation checks page ownership and response controls. The normal import
    # also checks the current source, source coverage, skills and saved review.
    plan = lesson_quality.resolve_readings(plan, packet['context']['source_requirements'])
    plan = lesson_quality.coherent_readings(plan)
    compiled = guide.build(packet['package']['sentences'], plan, faithful=True, instruction_only=True)
    lesson_quality.validate(compiled, packet['context']['source_requirements'])
    if book_questions.enabled(packet['context']):
        book_questions.validate_activities(guide.guide_activities(compiled), packet['context'])
    return script


def request(client, method, path, **kwargs):
    response = client.request(method, path, **kwargs)
    response.raise_for_status()
    return response.json()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--server', default='http://127.0.0.1:8000')
    sub = parser.add_subparsers(dest='command', required=True)
    export = sub.add_parser('export', help='Read-only source packet; never generates a lesson or audio')
    export.add_argument('--learner', type=int, required=True)
    export.add_argument('--topic', type=int, required=True)
    export.add_argument('--out', type=Path, required=True)
    revise = sub.add_parser('revise', help='Export a lesson with its current saved script as script.json, '
                            'to change it; import then saves it marked Revised')
    revise.add_argument('--learner', type=int, required=True)
    revise.add_argument('--topic', type=int, required=True)
    revise.add_argument('--out', type=Path, required=True)
    assign = sub.add_parser('assign', help='Assign the items of exercise pages shared with other lessons '
                            '(one small AI call per shared page set; a saved assignment is reused)')
    assign.add_argument('--topic', type=int, required=True)
    for command in ('validate', 'import'):
        step = sub.add_parser(command)
        step.add_argument('--packet', type=Path, required=True)
        step.add_argument('--script', type=Path, required=True)
    args = parser.parse_args()
    if args.command == 'validate':
        packet = read(args.packet)
        script = validate(packet, read(args.script))
        from tutoring.page_script import teaching_summary
        summary = teaching_summary(script, packet['package'])
        save(args.script.parent / 'teaching-review.json', summary)
        print('Valid structured lesson; no API calls or audio generation.')
        print(json.dumps(summary))
        return
    saved = None  # the saved script being revised, for the revise command
    with httpx.Client(base_url=args.server, timeout=240) as client:
        if args.command == 'assign':
            print(json.dumps(request(client, 'POST', f'/api/topics/{args.topic}/exercise-assignment'), ensure_ascii=False, indent=2))
            return
        if args.command == 'revise':
            reader = request(client, 'GET', '/api/tutor/reader', params={'learner': args.learner, 'topic': args.topic})
            guide = (reader.get('guide') or {}).get('guide_id')
            if not guide:
                raise SystemExit('This lesson has no saved script to revise; prepare it in the app first.')
            saved = request(client, 'GET', f'/api/tutor/guides/{guide}/script')
            args.command = 'export'
        if args.command == 'export':
            packet = request(client, 'POST', '/api/tutor/reader/guide', json={
                'learner': args.learner, 'topic': args.topic, 'dry_run': True,
                'export_inputs': True, 'prepare_voice': False})
            args.out.mkdir(parents=True, exist_ok=True)
            source = packet.pop('source_pdf_base64', None)
            if source:
                (args.out / 'source.pdf').write_bytes(base64.b64decode(source, validate=True))
            packet['learner'] = args.learner
            save(args.out / 'packet.json', packet)
            save(args.out / 'schema.json', packet['schema'])
            (args.out / 'prompt.txt').write_text(packet['prompt'], encoding='utf-8')
            if saved:
                packet['revises_guide_id'] = saved['guide_id']
                save(args.out / 'packet.json', packet)
                save(args.out / 'script.json', saved['script'])
                print(f"Exported {args.out.resolve()} with the saved script of {saved['guide_id']} ({saved['origin']}); "
                      'edit script.json, validate, then import (it is saved marked Revised).')
            else:
                print(f'Exported {args.out.resolve()}; inspect source.pdf before authoring script.json.')
        else:
            packet = read(args.packet)
            script = validate(packet, read(args.script))
            body = {'learner': packet['learner'], 'topic': packet['topic']['id'],
                'source_sha256': packet['package']['passage_sha256'],
                'expected_skill_version': packet['skill']['version'], 'script': script,
                **({'revises_guide_id': packet['revises_guide_id']} if packet.get('revises_guide_id') else {})}
            token = 'codex-lesson-' + hashlib.sha256(json.dumps(
                [body, packet['context']], sort_keys=True).encode()).hexdigest()
            result = request(client, 'POST', '/api/tutor/reader/guide/import', json=body,
                             headers={'Idempotency-Key': token})
            save(args.script.parent / 'saved-guide.json', result)
            print(json.dumps({'guide_id': result['guide_id'], 'review': result.get('script_review'),
                'activities': len(result['activities']), 'voice_requested': False}, ensure_ascii=False))


if __name__ == '__main__':
    main()
