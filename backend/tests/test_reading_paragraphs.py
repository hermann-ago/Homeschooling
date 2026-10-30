"""Paragraph layout must not alter narration identities or sentence positions."""
import copy
import pytest

from tutoring import guide, passages


def make(text, faithful=True):
    source = passages.split_sentences('An older extraction with no useful paragraphs.')
    plan = {'mode': 'tidy', 'segments': [{'type': 'intro', 'text': 'Listen to the story.'},
        {'type': 'read', 'text': text}, {'type': 'recap', 'text': 'We can return to it.'}]}
    return guide.build(source, plan, faithful=faithful, instruction_only=True)


@pytest.mark.parametrize('faithful', [False, True])
def test_faithful_reading_keeps_paragraphs_and_sentence_audio_identity(faithful):
    text = 'A Great Storm\n\nThe boat left the harbour. Jonathan hoped for adventure.\n\nThe wind rose. Waves tossed the boat.'
    result = make(text, faithful=faithful)
    book = [sentence for sentence in result['sentences'] if sentence['kind'] == 'book']
    assert [s['paragraphBoundary'] for s in book] == [True, True, False, True, False]
    assert book[1]['paragraphIndex'] == book[2]['paragraphIndex']
    assert book[2]['paragraphIndex'] != book[3]['paragraphIndex']
    assert result['segments'][1]['text'] == text
    without_layout = [{k: v for k, v in s.items() if k not in ('paragraphIndex', 'paragraphBoundary')}
                      for s in result['sentences']]
    assert guide.guide_sha(result['sentences']) == guide.guide_sha(without_layout)


def test_original_sentence_ranges_keep_their_source_paragraphs():
    source = passages.split_sentences('One sentence. Another sentence.\n\nA new paragraph.')
    result = guide.build(source, {'mode': 'expand', 'segments': [{'type': 'read', 'from': 0, 'to': 2}]})
    assert [s['source'] for s in result['sentences']] == [0, 1, 2]
    assert [s['paragraphBoundary'] for s in result['sentences']] == [True, False, True]


def test_legacy_display_recovers_only_exact_authored_text_without_mutating_saved_content():
    text = 'The boat left. Jonathan hoped for adventure.\n\nA storm arrived.'
    old = make(' '.join(text.split()))
    frozen = copy.deepcopy(old)
    context = {'teaching_script': {'script': {'turns': [{'type': 'read', 'text': text}]}}}
    shown = guide.display_sentences(old, context)
    book = [sentence for sentence in shown if sentence['kind'] == 'book']
    assert [s['paragraphBoundary'] for s in book] == [True, False, True]
    assert guide.guide_sha(shown) == guide.guide_sha(old['sentences'])
    assert old == frozen
    context['teaching_script']['script']['turns'][0]['text'] = 'Different words.\n\nA storm arrived.'
    assert guide.display_sentences(old, context) == old['sentences']
