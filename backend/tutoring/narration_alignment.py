"""Local, checked script/audio alignment. Never invent timings from text length.

Only generated narrator audio is processed. Models are installed explicitly;
lesson requests never download assets or send audio to an alignment provider.
"""
from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import re
import threading
import unicodedata
import wave

VERSION = 'wav2vec2-ctc-v5'
ASSETS = {
    'pt-BR': {
        'repo': 'onnx-community/wav2vec2-large-xlsr-53-portuguese-ONNX',
        'revision': '6f425223d83cd1ad134c007798c47f2e122744fd',
        'model_file': 'onnx/model_q4.onnx',
        'hashes': {'model.onnx': 'deb83887f3ef7af9b9a103ae243fcca3cff6704f10738258128a4db62e780704',
                   'vocab.json': 'c556e19617e216947d0a0a6f5b029ba4bf2cc54c005854e0960a1bf64bf0320b',
                   'preprocessor_config.json': '2c594304e9d9832162bedd5345051df29e8daf458a845cbed58c6ede23ceeae3'}},
    'en-US': {
        'repo': 'onnx-community/wav2vec2-base-960h-ONNX',
        'revision': '729c1a6730fb549c20a1c73a3d3f96f11020225e',
        'model_file': 'onnx/model.onnx',
        'model_name': 'model_fp32.onnx',
        'hashes': {'model_fp32.onnx': '00b7cc69516c1ab63c429e63a2b543e4d42bb77441ec5b98ee935de175b00de1',
                   'vocab.json': '4178db26b3c7570f6a47f14ac6a1c7b32950b8c2800fb097287e53776934f1c5',
                   'preprocessor_config.json': '8cdfd65ff4115423185a1512bdae100e2e0cd744f5b322417429944aaafd0827'}},
}
_engines = {}
_lock = threading.RLock()


class AlignmentError(ValueError):
    pass


def folder(ctx, language):
    host = getattr(ctx, 'live', None) or ctx
    return host.config.dir / 'models' / 'narration-alignment-v1' / language


def available(ctx, language):
    return (language in ASSETS and importlib.util.find_spec('onnxruntime') is not None
            and importlib.util.find_spec('numpy') is not None
            and all((folder(ctx, language) / name).is_file() for name in ASSETS[language]['hashes']))


def _engine(ctx, language):
    root = folder(ctx, language).resolve()
    if root not in _engines:
        if not available(ctx, language):
            raise AlignmentError('Install the local narrator alignment model before preparing larger audio blocks.')
        for name, expected in ASSETS[language]['hashes'].items():
            with (root / name).open('rb') as source:
                if hashlib.file_digest(source, 'sha256').hexdigest() != expected:
                    raise AlignmentError('The local alignment model failed its integrity check.')
        import onnxruntime as ort
        options = ort.SessionOptions()
        options.intra_op_num_threads = 2
        options.inter_op_num_threads = 1
        session = ort.InferenceSession(str(root / ASSETS[language].get('model_name','model.onnx')), sess_options=options,
                                       providers=['CPUExecutionProvider'])
        _engines[root] = session, json.loads((root / 'vocab.json').read_text(encoding='utf-8'))
    return _engines[root]


def normalize(text, language='pt-BR'):
    # Ordinary whole numbers have an unambiguous spoken form. Expressions need
    # an explicitly authored spoken form; never guess a mathematical reading.
    text = unicodedata.normalize('NFC', text).lower().replace('’', "'")
    # Locale-correct grouped integers are not decimal expressions. Keep this
    # normalization acoustic-only: the book and saved script retain their digits.
    separator = '.' if language == 'pt-BR' else ','
    grouped = rf'(?<![\w.,])\d{{1,3}}(?:{re.escape(separator)}\d{{3}})+(?!\w|[.,]\d)'
    text = re.sub(grouped, lambda m: m[0].replace(separator, ''), text)
    if re.search(r'[@=+*/%€£$]|\d[.,]\d', text):
        raise AlignmentError('Use a checked spoken form for numbers or mathematical symbols in the narrator script.')
    if re.search(r'\d', text):
        try:
            from num2words import num2words
            text = re.sub(r'\b\d+\b', lambda m: num2words(int(m[0]), lang='pt_BR' if language == 'pt-BR' else 'en'), text)
        except (ImportError, OverflowError, ValueError) as exc:
            raise AlignmentError('The narrator script needs a supported spoken number form.') from exc
    if re.search(r'\d', text):
        raise AlignmentError('Use an explicit spoken form for mixed numbers and letters.')
    if language == 'pt-BR':
        # Acoustic spelling of the isolated letter name /ke/. The CTC model
        # decodes a spoken Q as "ke"; sending the glyph alone cannot align a
        # phonics exercise. This affects alignment only, never script/display.
        text = re.sub(r'\bq\b', 'ke', text)
    return ' '.join(re.findall(r"[^\W\d_]+(?:'[^\W\d_]+)*", text, re.UNICODE))


def validate_script(ctx, sentences, language):
    vocab = json.loads((folder(ctx, language) / 'vocab.json').read_text(encoding='utf-8'))
    upper = 'A' in vocab and 'a' not in vocab
    for sentence in sentences:
        text = normalize(sentence['text'], language).replace(' ', '|')
        if not text or any(c not in vocab for c in (text.upper() if upper else text)):
            raise AlignmentError('The script needs a checked spoken form for letters unsupported by its alignment model.')


def _wav(data):
    import numpy as np
    try:
        with wave.open(io.BytesIO(data)) as source:
            if source.getnchannels() != 1 or source.getsampwidth() != 2 or source.getframerate() not in (16000, 24000):
                raise AlignmentError('Alignment needs mono 16-bit narrator WAV audio at 16 or 24 kHz.')
            rate = source.getframerate()
            samples = np.frombuffer(source.readframes(source.getnframes()), dtype='<i2').astype(np.float32) / 32768
    except (wave.Error, EOFError) as exc:
        raise AlignmentError('The saved narrator WAV is incomplete or unreadable.') from exc
    duration = len(samples) / rate
    if not .1 <= duration <= 660:
        raise AlignmentError('Narrator alignment supports blocks up to eleven minutes.')
    if rate != 16000:
        # Low-pass before 24 -> 16 kHz downsampling; no heavyweight audio runtime.
        n = np.arange(-31, 32)
        kernel = np.sinc(n * .63) * np.hamming(len(n))
        kernel /= kernel.sum()
        samples = np.convolve(samples, kernel, mode='same').astype(np.float32)
        samples = np.interp(np.arange(int(duration * 16000)) * rate / 16000,
                            np.arange(len(samples)), samples).astype(np.float32)
    return samples, duration


def _emissions(session, samples):
    import numpy as np
    probabilities, times = [], []
    # Bounded context windows prevent long recordings exhausting host memory.
    stride, context = 12 * 16000, 8000
    for first in range(0, len(samples), stride):
        last = min(first + stride, len(samples))
        lo, hi = max(0, first - context), min(len(samples), last + context)
        window = samples[lo:hi]
        if len(window) < 400:
            continue
        values = ((window - window.mean()) / np.sqrt(window.var() + 1e-7))[None, :].astype(np.float32)
        inputs = {'input_values': values}
        if any(item.name == 'attention_mask' for item in session.get_inputs()):
            inputs['attention_mask'] = np.ones(values.shape, dtype=np.int64)
        logits = session.run(None, inputs)[0][0].astype(np.float32)
        logits -= logits.max(axis=-1, keepdims=True)
        logp = logits - np.log(np.exp(logits).sum(axis=-1, keepdims=True))
        centers = (lo + np.arange(len(logp)) * 320 + 200) / 16000
        keep = (centers >= first / 16000) & (centers < last / 16000)
        probabilities.append(logp[keep])
        times.append(centers[keep])
    if not probabilities:
        raise AlignmentError('The narration contains no alignable audio.')
    return np.concatenate(probabilities), np.concatenate(times)


def ctc_path(logp, tokens, blank):
    """Viterbi CTC path with explicit blanks and repeated-letter constraints."""
    import numpy as np
    frames, _ = logp.shape
    if not tokens or frames * (2 * len(tokens) + 1) > 160_000_000:
        raise AlignmentError('The alignment block exceeds the local processing limit.')
    labels = np.full(2 * len(tokens) + 1, blank, dtype=np.int32)
    labels[1::2] = tokens
    skip = np.zeros(len(labels), dtype=bool)
    skip[2:] = (labels[2:] != blank) & (labels[2:] != labels[:-2])
    back = np.zeros((frames, len(labels)), dtype=np.uint8)
    previous = np.full(len(labels), -np.inf, dtype=np.float32)
    previous[0] = logp[0, blank]
    previous[1] = logp[0, labels[1]]
    for frame in range(1, frames):
        one = np.r_[-np.inf, previous[:-1]]
        two = np.r_[-np.inf, -np.inf, previous[:-2]]
        two[~skip] = -np.inf
        choices = np.stack((previous, one, two))
        back[frame] = choices.argmax(axis=0)
        previous = choices.max(axis=0) + logp[frame, labels]
    state = len(labels) - 1 if previous[-1] >= previous[-2] else len(labels) - 2
    if not np.isfinite(previous[state]):
        raise AlignmentError('The complete script cannot be located in this recording.')
    spans = [[] for _ in tokens]
    for frame in range(frames - 1, -1, -1):
        if state % 2:
            spans[state // 2].append(frame)
        if frame:
            state -= int(back[frame, state])
    if any(not span for span in spans):
        raise AlignmentError('The recording does not cover the complete narrator script.')
    return [sorted(span) for span in spans]


def align_emissions(logp, times, sentences, vocab, duration, language='pt-BR'):
    """Checked acoustic timings; rejects missing/low-confidence script coverage."""
    import numpy as np
    import difflib
    texts = [normalize(s['text'], language=language) for s in sentences]
    if any(not text for text in texts):
        raise AlignmentError('Every narrated sentence needs alignable words.')
    upper = 'A' in vocab and 'a' not in vocab
    blank = vocab.get('<pad>', 0)
    # An independent greedy decoding check guards against force-fitting a script
    # onto silence, an unrelated recording, or omitted/repeated passages.
    inverse = {value: key for key, value in vocab.items()}
    decoded, previous = [], None
    for token in logp.argmax(axis=-1).tolist():
        if token != blank and token != previous:
            decoded.append(inverse.get(token, ''))
        previous = token
    hypothesis = ''.join(decoded).lower().replace('|', ' ')
    spoken_forms = []
    if language == 'en-US':
        # A printed year such as 1421 may be spoken as "fourteen twenty-one".
        # Accept only that SAME integer, heard independently at the exact source
        # position. Missing or different years must still fail acoustic checks.
        from num2words import num2words
        words = ' '.join(texts).split()
        heard = hypothesis.split()
        edits = difflib.SequenceMatcher(None,words,heard,autojunk=False).get_opcodes()
        def boundary(position):
            for tag,lo,hi,start,stop in edits:
                if tag=='equal' and lo<=position<=hi:return start+position-lo
                if position==lo:return start
                if position==hi:return stop
            return None
        offset=0
        for number,text in enumerate(texts):
            tokens=text.split();replacements=[]
            for match in re.finditer(r'(?<![\w.,])(?:1\d{3}|20\d{2})(?!\w|[.,]\d)',sentences[number]['text']):
                value=int(match[0]);cardinal=normalize(match[0],'en-US').split()
                alternative=normalize(num2words(value,to='year',lang='en'),'en-US').split()
                locations=[i for i in range(len(tokens)-len(cardinal)+1) if tokens[i:i+len(cardinal)]==cardinal]
                if len(locations)!=1 or alternative==cardinal:continue
                lo=locations[0];hi=lo+len(cardinal)
                start,stop=boundary(offset+lo),boundary(offset+hi)
                if start is not None and stop is not None and heard[start:stop]==alternative:
                    replacements.append((lo,hi,alternative,value))
            for lo,hi,alternative,value in sorted(replacements,reverse=True):
                tokens[lo:hi]=alternative
                spoken_forms.append({'sentence':number,'integer':value,'kind':'year','spoken_form':' '.join(alternative)})
            texts[number]=' '.join(tokens)
            offset+=len(text.split())
        # The recognizer may spell the SAME spoken letter as C or SEE (B or
        # BEE). Accept that orthographic alternative only when independently
        # decoded as one word at this exact script position. Never insert a
        # missing label or use this rule for ordinary words or abbreviations.
        words = ' '.join(texts).split()
        heard = hypothesis.split()
        replacements = {i:heard[j] for tag,i,end,j,stop in
            difflib.SequenceMatcher(None,words,heard,autojunk=False).get_opcodes()
            if tag == 'replace' and end-i == stop-j == 1
            and (words[i],heard[j]) in (('c','see'),('b','bee'))}
        offset = 0
        for number,text in enumerate(texts):
            if (offset in replacements and re.fullmatch(r'[BC][.)]',sentences[number]['text'].strip())):
                texts[number] = replacements[offset]
                spoken_forms.append({'sentence':number,'spoken_form':texts[number]})
            offset += len(text.split())
        # The sea/letter-C homophone is also a recognizer spelling ambiguity.
        # Accept only an independently decoded C replacing one existing SEA at
        # the same word position. This changes acoustic spelling, not source
        # content, and cannot fill an omitted word or accept a different sea.
        words = ' '.join(texts).split()
        sea_as_c = {i for tag,i,end,j,stop in
            difflib.SequenceMatcher(None,words,heard,autojunk=False).get_opcodes()
            if tag == 'replace' and end-i == stop-j == 1
            and words[i] == 'sea' and heard[j] == 'c'}
        offset = 0
        for number,text in enumerate(texts):
            tokens = text.split()
            for position,word in enumerate(tokens):
                if offset+position in sea_as_c:
                    tokens[position] = 'c'
                    spoken_forms.append({'sentence':number,'kind':'homophone','source_word':'sea','spoken_form':'c'})
            texts[number] = ' '.join(tokens)
            offset += len(tokens)
        # English Kiev may be spoken in two syllables; the recognizer also writes
        # it as KIIV or splits those syllables into KI/KEI OF. Match only this
        # exact independently decoded pronunciation at the existing word's
        # position. The source spelling, options and answer assessment stay
        # unchanged. Missing words, other cities and changed labels still fail.
        words = ' '.join(texts).split()
        name_forms = {i: heard[j:stop] for tag,i,end,j,stop in
            difflib.SequenceMatcher(None,words,heard,autojunk=False).get_opcodes()
            if tag == 'replace' and end-i == 1 and words[i] == 'kiev'
            and tuple(heard[j:stop]) in (('kyiv',), ('kiiv',), ('kei','of'), ('ki','of'))}
        offset = 0
        for number,text in enumerate(texts):
            tokens = text.split()
            for position in reversed(range(len(tokens))):
                alternative = name_forms.get(offset+position)
                if alternative:
                    tokens[position:position+1] = alternative
                    spoken_forms.append({'sentence':number,'kind':'pronunciation',
                                         'source_word':'kiev','spoken_form':' '.join(alternative)})
            texts[number] = ' '.join(tokens)
            offset += len(text.split())
    joined = '|'.join(text.replace(' ', '|') for text in texts)
    script = joined.upper() if upper else joined
    if any(char not in vocab for char in script):
        raise AlignmentError('This script contains letters unsupported by its language alignment model.')
    tokens = [vocab[char] for char in script]
    expected = ' '.join(texts)
    similarity = difflib.SequenceMatcher(None, expected, hypothesis, autojunk=False).ratio()
    if similarity < .72:
        raise AlignmentError('The spoken recording differs from the saved script; its timing needs review.')
    spans = ctc_path(logp, tokens, blank)
    starts, ends, scores, position = [], [], [], 0
    sentence_probabilities = []
    for number, text in enumerate(texts):
        length = len(text)
        indices = range(position, position + length)
        probabilities = [float(np.exp(logp[spans[i], tokens[i]]).max()) for i in indices if script[i] != '|']
        confidence = float(np.mean(probabilities))
        low = sum(p < .12 for p in probabilities) / len(probabilities)
        sentence_probabilities.append(probabilities)
        start = max(0., float(times[spans[position][0]]) - .01)
        end = min(duration, float(times[spans[position + length - 1][-1]]) + .01)
        if end <= start or end - start > max(8., len(text.split()) * 2.5):
            raise AlignmentError('A sentence has an implausible audio range; its timing needs review.')
        starts.append(start)
        ends.append(end)
        scores.append(round(confidence, 4))
        position += length + 1
    groups = []
    short_groups = []
    protected = {0,len(sentences)} | {i for i,s in enumerate(sentences) if s.get('_alignment_boundary_before')}
    for number, probabilities in enumerate(sentence_probabilities):
        confidence = float(np.mean(probabilities))
        low = sum(p < .12 for p in probabilities) / len(probabilities)
        if confidence >= .48 and low <= .18:
            continue
        # Very short spoken cues or glossary entries give CTC little context.
        # Verify them within a bounded spoken unit in the SAME engine activity,
        # retaining a strict individual confidence floor. Never cross a stop,
        # forgive an absent cue, or use this without explicit activity cuts.
        if (any(s.get('_alignment_boundary_before') for s in sentences)
                and len(texts[number].split())<=6 and len(texts[number])>=3
                and confidence>=.55 and low<=.4):
            lo=max(i for i in protected if i<=number)
            hi=min(i for i in protected if i>number)-1
            selected=list(range(lo,hi+1))
            if (1<len(selected)<=8 and sum(len(texts[i]) for i in selected)<=600
                    and all(sentences[i].get('kind')==sentences[number].get('kind') for i in selected)):
                combined=[p for i in selected for p in sentence_probabilities[i]]
                if float(np.mean(combined))>=.80 and sum(p<.12 for p in combined)/len(combined)<=.12:
                    short_groups.append(selected)
                    continue
        # A printed choice label such as "C." is part of its following option,
        # not a complete spoken sentence. Validate that reading unit together,
        # only inside one source range and never at/across an activity cut.
        label = re.fullmatch(r'([ABC])[.)]', sentences[number]['text'].strip())
        following = sentences[number+1] if number+1 < len(sentences) else {}
        earlier_labels = [s['text'].strip() for s in sentences[max(0,number-4):number]
                          if s.get('source') == sentences[number].get('source') and s.get('kind') == 'book']
        if (language == 'en-US' and label and label[1] in ('B','C') and 'A.' in earlier_labels
                and (label[1] == 'B' or 'B.' in earlier_labels)
                and sentences[number].get('kind') == following.get('kind') == 'book'
                and sentences[number].get('source') is not None
                and sentences[number].get('source') == following.get('source')
                and number not in protected and number+1 not in protected
                and not sentences[number].get('pause_after') and min(probabilities) >= .12):
            combined = probabilities + sentence_probabilities[number+1]
            if float(np.mean(combined)) >= .48 and sum(p < .12 for p in combined)/len(combined) <= .18:
                groups.append([number, number+1])
                continue
        raise AlignmentError(f'Sentence {number + 1} has uncertain acoustic alignment ({confidence:.2f}; {low:.2f}); its timing needs review.')
    if starts[0] > 2.5 or duration - ends[-1] > 3:
        raise AlignmentError('Unexpected speech or silence outside the script needs review.')
    if any(b < a for a, b in zip(ends, starts[1:])):
        raise AlignmentError('Overlapping sentence timings need review.')
    # Put boundaries in the measured gaps rather than estimating from word count.
    cuts = [0.] + [(a + b) / 2 for a, b in zip(ends, starts[1:])]
    return {'sentenceStarts': cuts, 'sentenceEnds': ends, 'duration': duration,
            'alignment': {'version': VERSION, 'similarity': round(similarity, 4), 'sentence_scores': scores,
                          'choice_label_groups':groups, 'short_utterance_groups':short_groups,'spoken_forms':spoken_forms}}


def align(ctx, wav_data, sentences, language):
    with _lock:
        session, vocab = _engine(ctx, language)
        samples, duration = _wav(wav_data)
        import numpy as np
        path=_emission_path(ctx,wav_data,language)
        try:
            with np.load(path,allow_pickle=False) as saved:
                if str(saved['audio_sha256'])!=hashlib.sha256(wav_data).hexdigest():raise ValueError('Wrong recording cache')
                logp,times=saved['logp'],saved['times']
                _check_emissions(logp,times)
        except (OSError,ValueError,KeyError,EOFError):
            logp, times = _emissions(session, samples)
            store_emissions(ctx,wav_data,language,logp,times)
        return align_emissions(logp, times, sentences, vocab, duration, language)


def _emission_path(ctx,wav_data,language):
    host=getattr(ctx,'live',None) or ctx
    key=hashlib.sha256(json.dumps(['emissions-v1',language,ASSETS[language]['revision'],
        hashlib.sha256(wav_data).hexdigest()]).encode()).hexdigest()
    return host.config.dir/'cache'/'narration-emissions'/f'{key}.npz'


def _check_emissions(logp,times):
    import numpy as np
    if (logp.ndim!=2 or times.ndim!=1 or len(logp)!=len(times) or not len(times)
            or not np.isfinite(logp).all() or not np.isfinite(times).all() or np.any(np.diff(times)<=0)):
        raise ValueError('Invalid cached acoustic emissions')


def store_emissions(ctx,wav_data,language,logp,times):
    """Cache local acoustic analysis; script coverage is still checked on every use."""
    import numpy as np
    import os
    import tempfile
    _check_emissions(logp,times)
    path=_emission_path(ctx,wav_data,language)
    path.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent,suffix='.npz',delete=False) as output:
        temporary=output.name
        np.savez_compressed(output,logp=logp,times=times,audio_sha256=hashlib.sha256(wav_data).hexdigest())
    os.replace(temporary,path)
