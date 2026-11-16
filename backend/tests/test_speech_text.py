from types import SimpleNamespace

import pytest

from tutoring import inworld_audio, narration, script_review
from tutoring.speech_text import for_voice, speakable


@pytest.mark.parametrize('shown, said', [
    ('Termina: ___________________________________', 'Termina:'),
    ('The _____ was a substitute king.', 'The … was a substitute king.'),
    ('Most people died within __________.', 'Most people died within …'),
    ('Escreva: Va__o, Ce__ão', 'Escreva: Va … o, Ce … ão'),
    ('Item 3: Bal( )o.', 'Item 3: Bal … o.'),
    ('( ) Lili gosta de varrer.', 'Lili gosta de varrer.'),
    ('1, 2, 4, 7, 11, ___, ___, ___', '1, 2, 4, 7, 11, …'),
    ('Facts. • The language is Hindi.', 'Facts. The language is Hindi.'),
    ('tethered | timidly | reproachful', 'tethered, timidly, reproachful'),
    ('**Note:** read #3', 'Note: read 3'),
    ('Muito bem! 🎉 Você acertou.', 'Muito bem! Você acertou.'),
])
def test_page_marks_are_not_read_aloud(shown, said):
    assert speakable(shown) == said


@pytest.mark.parametrize('words', [
    '74 - 48 = 52 - 29 =', '> Greater Than < Less Than = Equal To', 'It costs $2.3 billion at 25°C.',
    'Wait... what?', 'O til (~) aparece.', 'Dias depois o leão caiu numa rede .',
])
def test_numbers_signs_and_untouched_sentences_stay_as_written(words):
    assert speakable(words) == words


def test_a_labelled_answer_line_is_said_as_a_list_word_and_no_sentence_disappears():
    passage = {'passage_sha256': 'same', 'sentences': [{'text': 'Separe as sílabas das seguintes palavras:', 'paragraphIndex': 0},
        {'text': 'Termina: ______', 'paragraphIndex': 1}, {'text': '______', 'paragraphIndex': 2}]}
    spoken = for_voice(passage)
    assert [s['text'] for s in spoken['sentences']] == ['Separe as sílabas das seguintes palavras:', 'Termina.', '…']
    assert spoken['sentences'][0] is passage['sentences'][0] and spoken['passage_sha256'] == 'same'
    assert passage['sentences'][1]['text'] == 'Termina: ______'


def test_every_voice_receives_the_cleaned_words_while_the_review_sees_the_lesson(monkeypatch):
    reviewed, sent = [], []
    monkeypatch.setattr(script_review, 'require_audio', lambda ctx, passage: reviewed.append(passage['sentences'][0]['text']))
    monkeypatch.setattr(inworld_audio, 'generate', lambda ctx, topic, passage, **options: sent.append(passage['sentences'][0]['text']) or {})
    ctx = SimpleNamespace(config={'tts': {'provider': 'inworld'}})
    narration.generate(ctx, {'id': 'topic'}, {'passage_sha256': 'x', 'sentences': [{'text': 'Menino: ______'}]})
    assert reviewed == ['Menino: ______'] and sent == ['Menino.']
