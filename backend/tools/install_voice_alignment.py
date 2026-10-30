"""Explicitly install pinned CPU alignment assets; never change narrator settings."""
import argparse
import hashlib
import json
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config import data_dir
from tutoring.narration_alignment import ASSETS


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--language', choices=ASSETS, action='append')
    args = parser.parse_args()
    for language in args.language or ASSETS:
        spec = ASSETS[language]
        root = data_dir() / 'models' / 'narration-alignment-v1' / language
        root.mkdir(parents=True, exist_ok=True)
        provenance = {}
        for name, expected in spec['hashes'].items():
            source_name = spec['model_file'] if name == spec.get('model_name','model.onnx') else name
            url = f"https://huggingface.co/{spec['repo']}/resolve/{spec['revision']}/{source_name}"
            dest = root / name
            if not dest.exists():
                print('Downloading', language, name, flush=True)
                temporary = dest.with_suffix(dest.suffix + '.partial')
                urllib.request.urlretrieve(url, temporary)
                with temporary.open('rb') as source:
                    if hashlib.file_digest(source, 'sha256').hexdigest() != expected:
                        raise ValueError('Alignment model download failed its integrity check')
                temporary.replace(dest)
            with dest.open('rb') as source:
                if hashlib.file_digest(source, 'sha256').hexdigest() != expected:
                    raise ValueError('Existing alignment asset failed its integrity check')
            provenance[name] = {'url': url, 'sha256': expected, 'bytes': dest.stat().st_size}
        (root / 'assets.json').write_text(json.dumps(provenance, indent=2), encoding='utf-8')
        print('Installed narrator alignment:', language, flush=True)


if __name__ == '__main__':
    main()
