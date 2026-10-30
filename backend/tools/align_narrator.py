"""Align an existing generated narrator WAV and script, without any provider call.

The script JSON contains a sentences array and optional activity start indices.
Outputs acoustic timings and bounded playback clips; source files stay intact.
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config import HostConfig
from tutoring import narration_alignment as alignment
from tutoring.aligned_audio import clip


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--audio', required=True, type=Path)
    parser.add_argument('--script', required=True, type=Path)
    parser.add_argument('--language', choices=alignment.ASSETS, required=True)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--data-dir', type=Path)
    args = parser.parse_args()
    ctx = SimpleNamespace(config=HostConfig(args.data_dir)) if args.data_dir else SimpleNamespace(config=HostConfig())
    script_bytes = args.script.read_bytes()
    package = json.loads(script_bytes)
    sentences = package['sentences'] if isinstance(package, dict) else package
    data = args.audio.read_bytes()
    result = alignment.align(ctx, data, sentences, args.language)
    result.update(language=args.language, audio_sha256=hashlib.sha256(data).hexdigest(),
                  script_sha256=hashlib.sha256(script_bytes).hexdigest())
    boundaries = {0, len(sentences)}
    if isinstance(package, dict) and package.get('activities'):
        boundaries.update(a['start_sentence'] for a in package['activities'])
    else:
        boundaries.update(range(len(sentences)))
    if any(not isinstance(i, int) or not 0 <= i <= len(sentences) for i in boundaries):
        raise ValueError('Activity boundaries must refer to the supplied script')
    args.output.mkdir(parents=True, exist_ok=True)
    tracks = []
    cuts = sorted(boundaries)
    for index, (first, last) in enumerate(zip(cuts, cuts[1:])):
        start = result['sentenceStarts'][first]
        end = result['sentenceStarts'][last] if last < len(sentences) else result['duration']
        recording = clip(data, start, end)
        path = args.output / f'clip-{index+1:03d}.wav'
        path.write_bytes(recording)
        tracks.append({'file': path.name, 'startSentence': first, 'sentenceCount': last-first,
                       'sentenceStarts': [t-start for t in result['sentenceStarts'][first:last]],
                       'duration': end-start, 'sha256': hashlib.sha256(recording).hexdigest()})
    result['tracks'] = tracks
    (args.output / 'alignment.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'status': 'aligned', 'sentences': len(sentences), 'clips': len(tracks),
                      'seconds': round(result['duration'], 2), 'output': str(args.output.resolve())}))


if __name__ == '__main__':
    main()
