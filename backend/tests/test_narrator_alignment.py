import io
import wave

import pytest
np = pytest.importorskip('numpy')

from tutoring.narration_alignment import AlignmentError, align_emissions, ctc_path, normalize
from tutoring.aligned_audio import blocks, clip


def acoustic(text):
    vocab = {'<pad>': 0, '|': 1, **{char: i+2 for i, char in enumerate(sorted(set(text)-{'|'}))}}
    labels = [0]
    for char in text:
        labels += [vocab[char], vocab[char], 0]
    scores = np.full((len(labels), len(vocab)), -14., dtype=np.float32)
    scores[np.arange(len(labels)), labels] = -.001
    return scores, np.arange(len(labels))*.02+.01, vocab


def test_ctc_handles_repeated_letters_and_returns_acoustic_sentence_boundaries():
    logp, times, vocab = acoustic('little|cat|sits|still')
    result = align_emissions(logp, times, [{'text': 'Little cat.'}, {'text': 'Sits still.'}], vocab,
                             len(times)*.02, 'en-US')
    assert result['sentenceStarts'][0] == 0
    assert result['sentenceEnds'][0] < result['sentenceStarts'][1] < result['sentenceEnds'][1]
    assert result['alignment']['similarity'] == 1
    tokens = [vocab[c] for c in 'little|cat|sits|still']
    spans = ctc_path(logp, tokens, 0)
    assert len(spans) == len(tokens) and all(span for span in spans)


def test_unrelated_or_missing_audio_never_publishes_guessed_timings():
    logp, times, vocab = acoustic('cat|sits')
    for text in ('sits cat cat cat', 'cat sits little cat sits'):
        with pytest.raises(AlignmentError):
            align_emissions(logp, times, [{'text': text}], vocab, len(times)*.02, 'en-US')


def test_short_portuguese_cue_can_use_context_but_never_cross_an_activity_stop():
    from tutoring.narration_alignment import normalize
    text='urrou|imite|o|rugido|bem|forte'
    logp,times,vocab=acoustic(text)
    # Two uncertain cue characters; the cue still has positive independent
    # evidence, and its following instruction is acoustically clear.
    logp[1:3,vocab['u']]=-4
    logp[4:6,vocab['r']]=-4
    rows=[{'text':'Urrou!','kind':'teacher','_alignment_boundary_before':True},
          {'text':'Imite o rugido bem forte.','kind':'teacher'}]
    result=align_emissions(logp,times,rows,vocab,len(times)*.02,'pt-BR')
    assert result['alignment']['short_utterance_groups']==[[0,1]]
    with pytest.raises(AlignmentError):align_emissions(logp,times,[rows[0],{**rows[1],'_alignment_boundary_before':True}],vocab,len(times)*.02,'pt-BR')
    other,clock,lexicon=acoustic('imite|o|rugido|bem|forte')
    # Entirely missing speech cannot be rescued by its surrounding instruction.
    with pytest.raises(AlignmentError):align_emissions(other,clock,rows,lexicon,len(clock)*.02,'pt-BR')
    with pytest.raises(AlignmentError):
        align_emissions(np.full_like(logp, -4), times, [{'text': 'Cat sits.'}], vocab, len(times)*.02)


def test_numeric_year_accepts_only_the_same_year_actually_heard_at_its_position():
    logp,times,vocab=acoustic('work|began|in|fourteen|twenty|one|and|ended')
    rows=[{'text':'Work began in 1421.'},{'text':'And ended.'}]
    result=align_emissions(logp,times,rows,vocab,len(times)*.02,'en-US')
    assert result['alignment']['similarity']==1
    assert result['alignment']['spoken_forms']==[{'sentence':0,'integer':1421,'kind':'year','spoken_form':'fourteen twenty one'}]
    for text in ('Work began in 1422.','Work began in one thousand four hundred and twenty one.'):
        with pytest.raises(AlignmentError):
            align_emissions(logp,times,[{'text':text},{'text':'And ended.'}],vocab,len(times)*.02,'en-US')
    missing,t,v=acoustic('work|began|in|and|ended')
    with pytest.raises(AlignmentError):align_emissions(missing,t,rows,v,len(t)*.02,'en-US')


def test_choice_label_is_checked_with_its_option_without_crossing_activity_boundaries():
    text='a|kind|b|calm|c|sad'
    logp,times,vocab=acoustic(text)
    rows=[{'text':t,'kind':'book','source':0} for t in ('A.','Kind.','B.','Calm.','C.','Sad.')]
    label_at=text.rfind('|c|')+1
    frames=[label_at*3+1,label_at*3+2]
    logp[frames,vocab['c']]=np.log(.3)
    logp[frames,vocab['s']]=np.log(.7)
    duration=len(times)*.02
    result=align_emissions(logp,times,rows,vocab,duration,'en-US')
    assert result['alignment']['choice_label_groups']==[[4,5]]
    for boundary in (4,5):
        checked=[{**row,'_alignment_boundary_before':i==boundary} for i,row in enumerate(rows)]
        with pytest.raises(AlignmentError):align_emissions(logp,times,checked,vocab,duration,'en-US')
    logp[frames,vocab['c']]=np.log(.001)
    with pytest.raises(AlignmentError):align_emissions(logp,times,rows,vocab,duration,'en-US')


def test_phonics_and_whole_numbers_have_alignment_only_spoken_forms():
    assert normalize('Q, q.', 'pt-BR') == 'ke ke'
    assert normalize('Página 19.', 'pt-BR') == 'página dezenove'
    assert normalize('Page 19.', 'en-US') == 'page nineteen'
    assert normalize('9,999 buildings.', 'en-US') == normalize('9999 buildings.', 'en-US')
    assert normalize('9.999 edifícios.', 'pt-BR') == normalize('9999 edifícios.', 'pt-BR')
    for text,language in [('1,25','pt-BR'),('1.25','en-US'),('1,234.5','en-US'),('1.234,5','pt-BR')]:
        with pytest.raises(AlignmentError):normalize(text,language)
    assert normalize('C.', 'en-US') == 'c'
    assert normalize('Circle the cat.', 'en-US') == 'circle the cat'
    for text in ('3/4', '2 + 2', 'R$ 4', '1.25', '1st'):
        with pytest.raises(AlignmentError): normalize(text)


def test_sea_recognized_as_letter_c_is_acoustic_only_and_does_not_accept_a_changed_option():
    rows=[{'text':'Caspian Sea b.'}]
    logp,times,vocab=acoustic('caspian|c|b')
    result=align_emissions(logp,times,rows,vocab,len(times)*.02,'en-US')
    assert result['alignment']['similarity']==1
    assert rows==[{'text':'Caspian Sea b.'}]
    assert result['alignment']['spoken_forms']==[{'sentence':0,'kind':'homophone','source_word':'sea','spoken_form':'c'}]
    for wrong in ['caspian|red|b','caspian|b']:
        logp,times,vocab=acoustic(wrong)
        with pytest.raises(AlignmentError):
            align_emissions(logp,times,rows,vocab,len(times)*.02,'en-US')


def test_spoken_english_choice_letter_requires_actual_audio_even_at_block_start():
    logp,times,vocab=acoustic('see|sad|c')
    # Include the ordinary glyph in the model's vocabulary too.
    rows=[{'text':'C.','_alignment_boundary_before':True},{'text':'Sad.'},{'text':'C.'}]
    assert align_emissions(logp,times,rows,vocab,len(times)*.02,'en-US')['alignment']['similarity']==1
    for k in range(3):
        logp[[k*3+1,k*3+2],vocab['see'[k]]]=-14
    with pytest.raises(AlignmentError):
        align_emissions(logp,times,rows,vocab,len(times)*.02,'en-US')


@pytest.mark.parametrize('heard', ['kei|of|c', 'ki|of|c', 'kiiv|c', 'kyiv|c'])
def test_kiev_acoustic_spelling_keeps_source_and_choice_identity(heard):
    rows = [{'text': 'Kiev c.'}]
    logp, times, vocab = acoustic(heard)
    result = align_emissions(logp, times, rows, vocab, len(times)*.02, 'en-US')
    assert result['alignment']['similarity'] == 1
    assert rows == [{'text': 'Kiev c.'}]
    assert result['alignment']['spoken_forms'][0]['source_word'] == 'kiev'
    for missing_or_different in ('c', 'kyoto|c', 'kei|of|b'):
        bad, t, v = acoustic(missing_or_different)
        with pytest.raises(AlignmentError):
            align_emissions(bad, t, rows, v, len(t)*.02, 'en-US')


def test_bigger_blocks_cross_activity_stops_but_stay_bounded():
    sentences = [{'text': 'A short instruction.', 'pause_after': f'action-{i}'} for i in range(38)]
    assert len(blocks(sentences)) == 1
    assert sum(count for _, count, _ in blocks(sentences*10)) == 380
    assert all(len(text) <= 2400 and len(text.split()) <= 420 for _, _, text in blocks(sentences*10))
    with pytest.raises(ValueError): blocks([{'text': 'a'*2500}])


def test_cut_uses_measured_samples_and_does_not_include_next_activity():
    output = io.BytesIO()
    with wave.open(output, 'wb') as target:
        target.setparams((1,2,16000,0,'NONE','not compressed'))
        target.writeframes(np.r_[np.ones(8000)*1000, np.ones(8000)*2000].astype('<i2').tobytes())
    with wave.open(io.BytesIO(clip(output.getvalue(), 0, .5))) as source:
        samples = np.frombuffer(source.readframes(source.getnframes()), dtype='<i2')
    assert len(samples) == 8000 and set(samples) == {1000}
    with pytest.raises(AlignmentError): clip(output.getvalue(), 0, 2)
