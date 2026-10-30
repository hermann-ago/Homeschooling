"""Create/validate portable book JSON without starting the server or using API tokens."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tutoring.book_companion import Companion, Envelope, digest, native


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    draft = sub.add_parser('draft')
    draft.add_argument('pdf', type=Path)
    draft.add_argument('--role', required=True, choices=['textbook', 'combined', 'workbook', 'test', 'answer_key', 'reference'])
    draft.add_argument('--edition', default='')
    draft.add_argument('--output', required=True, type=Path)
    schema = sub.add_parser('schema')
    schema.add_argument('--output', required=True, type=Path)
    seal = sub.add_parser('seal', help='Validate an edited body/envelope and recompute its checksum; does not mark pages checked')
    seal.add_argument('json', type=Path)
    seal.add_argument('--pdf', required=True, type=Path)
    seal.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    if args.command == 'schema':
        result = Envelope.model_json_schema()
    else:
        if args.command == 'draft':
            body = native(args.pdf.read_bytes(), args.pdf.name, args.role, args.edition)
        else:
            import hashlib
            value = json.loads(args.json.read_text(encoding='utf-8'))
            body = Companion.model_validate(value.get('contents', value)).model_dump()
            data = args.pdf.read_bytes()
            from pypdf import PdfReader
            import io
            if body['source']['sha256'] != hashlib.sha256(data).hexdigest() or body['source']['page_count'] != len(PdfReader(io.BytesIO(data)).pages):
                raise ValueError('The JSON must match the exact original PDF and page count')
        result = {'content_sha256': digest(body), 'contents': body}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(args.output.suffix + '.tmp')
    temporary.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    temporary.replace(args.output)
    print(json.dumps({'output': str(args.output.resolve()), 'status': 'schema' if args.command == 'schema' else 'validated',
                      'checked_pages': sum(p['status'] == 'checked' for p in result.get('contents', {}).get('pages', []))}))


if __name__ == '__main__':
    main()
