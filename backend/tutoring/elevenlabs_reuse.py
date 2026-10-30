"""Reuse exact text from saved provider responses, without a new speech request."""
import base64
import io
import json
import wave


def sections(passage, legacy_blocks):
    activities = passage.get('activities') or []
    cursor, result = 0, []
    for activity in activities:
        first, last = activity.get('start_sentence'), activity.get('end_sentence')
        if first != cursor or last is None or not first <= last < len(passage['sentences']):
            return legacy_blocks(passage['sentences'])
        for offset, count, text in legacy_blocks(passage['sentences'][first:last + 1]):
            result.append((first + offset, count, text))
        cursor = last + 1
    return result if cursor == len(passage['sentences']) else legacy_blocks(passage['sentences'])


def recordings(ctx, topic, passage, wanted, voice, rate, language, purpose, identity, model, validate):
    """Only exact substrings, in order, within one verified purchase job.

    The original request identity proves voice/model/language/speed. Never mix
    feedback or another learner's lesson. Provider timings supply every cut;
    all reused PCM and timing must validate before publication.
    """
    result = {}
    jobs = [j for j in ctx.ai.ledger.jobs() if j.get('topic_id') == topic['id']
            and j.get('purpose') == purpose and j.get('voice') == voice and j.get('model') == model]
    for job in reversed(jobs):
        if len(result) == len(wanted):
            break
        parts, text, cursor = [], '', 0
        for rid in job.get('request_ids', []):
            raw = ctx.ai.ledger.result(rid)
            if raw is None:
                # A gap must never be bridged as if its words were recorded.
                parts.append(None)
                text += '\0'
                cursor += 1
                continue
            value = json.loads(raw)
            original = ''.join((value.get('alignment') or {}).get('characters', []))
            if not original or identity(original, voice, language, rate) != rid:
                text += '\0'
                cursor += 1
                continue
            if text and not text.endswith('\0'):
                text += ' '
                cursor += 1
            parts.append((cursor, cursor + len(original), value))
            text += original
            cursor += len(original)
        for index, (first, count, needle) in wanted.items():
            if index in result:
                continue
            start = text.find(needle)
            while start >= 0 and ((start > 0 and not text[start - 1].isspace())
                                  or (start + len(needle) < len(text) and not text[start + len(needle)].isspace())):
                start = text.find(needle, start + 1)
            if start < 0:
                continue
            end, pcm, starts, duration = start + len(needle), bytearray(), [], 0.0
            sentence_offsets, position = [], start
            for sentence in passage['sentences'][first:first + count]:
                sentence_offsets.append(position)
                position += len(sentence['text']) + 1
            for part in parts:
                if part is None:
                    continue
                lo, hi, value = part
                if hi <= start or lo >= end:
                    continue
                # Validate the whole purchased response before trusting any cut.
                _, full_duration, _ = validate(value, [{'text': text[lo:hi]}])
                timing = value['alignment']['character_start_times_seconds']
                a, b = max(start, lo) - lo, min(end, hi) - lo
                begin = timing[a] if a else 0
                finish = timing[b] if b < hi - lo else full_duration
                frames = base64.b64decode(value['audio_base64'], validate=True)
                frame_a, frame_b = round(begin * 24000), round(finish * 24000)
                if not 0 <= frame_a < frame_b <= len(frames) // 2:
                    raise ValueError('A saved ElevenLabs cut is outside its recording')
                starts.extend(duration + timing[p - lo] - frame_a / 24000 for p in sentence_offsets
                              if max(start, lo) <= p < min(end, hi))
                pcm.extend(frames[frame_a * 2:frame_b * 2])
                duration += (frame_b - frame_a) / 24000
            if len(starts) != count or not duration:
                continue
            starts[0] = 0
            if any(b <= a for a, b in zip(starts, starts[1:])) or starts[-1] >= duration:
                continue
            output = io.BytesIO()
            with wave.open(output, 'wb') as wav:
                wav.setparams((1, 2, 24000, 0, 'NONE', 'not compressed'))
                wav.writeframes(pcm)
            result[index] = {'data': output.getvalue(), 'mime': 'audio/wav', 'duration': duration,
                             'sentenceStarts': starts, 'timing': 'provider-alignment', 'reused_from_job': job['id']}
    return result
