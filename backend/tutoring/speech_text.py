"""What the voice is sent: the lesson's words without the page furniture around them.

A lesson shows book text as printed, answer lines and boxes included ("Termina: ______",
"Bal( )o", "• a fact"). A voice reads those marks aloud or stumbles over them, so every
narration provider receives the sentences through `for_voice`. The text the child sees,
the guide and its hash are unchanged; only the spoken copy loses the marks. Numbers, math
signs and ordinary punctuation are words to a voice and stay.
"""
import re
import unicodedata

# An answer line or box: underscores, a row of dots or dashes, empty brackets.
GAP = re.compile(r'_+|\.{4,}|…{2,}|-{3,}|–{2,}|—{2,}|\(\s*\)|\[\s*\]')
PAUSE = '\x00'  # where a gap stood, until we know whether a pause belongs there
# Marks that only lay out a page or a chat message.
LAYOUT = re.compile(r'[*#`|•◦▪▫■□☐☑☒✓✔✗✘➢➤►▶◆◇○●]')
KEEP_SYMBOLS = set('°%$€£¢&@')


def _dropped(ch):
    """Emoji and other pictures; private and broken characters."""
    return ch not in KEEP_SYMBOLS and unicodedata.category(ch) in ('So', 'Cs', 'Co')


def speakable(text):
    """One sentence as the voice should hear it; empty when it held only marks.

    A blank the child fills in becomes a short pause ("The … was a king", "Va … o",
    "died within…"); a box or line that only marks where to write is dropped: an answer
    line after a label ("Termina: ____") and a tick box opening a line ("( ) Lili…").
    A sentence without such marks is returned untouched, so its recording stays valid."""
    text = str(text or '')
    if not (GAP.search(text) or LAYOUT.search(text) or any(_dropped(ch) for ch in text)):
        return text
    text = GAP.sub(f' {PAUSE} ', text)
    text = LAYOUT.sub(lambda mark: ', ' if mark.group(0) == '|' else ' ', text)
    text = ''.join(ch for ch in text if not _dropped(ch))
    text = re.sub(r'\s+', ' ', text).strip()
    text = re.sub(rf'{PAUSE}(?:[\s,;]*{PAUSE})+', PAUSE, text)  # "___, ___, ___" is one pause
    text = re.sub(rf'(^|[:(\[«“"])\s*{PAUSE}\s*', r'\1 ', text)
    text = text.replace(PAUSE, '…')
    text = re.sub(r'\s+', ' ', text).strip()
    text = re.sub(r'\s+([,.;:!?)\]»”])', r'\1', text)
    text = text.replace('….', '…')
    text = re.sub(r'([,;:])(?:\s*[,;:])+', r'\1', text)  # left behind where a mark sat between two
    text = re.sub(r'^[,;:\s]+', '', text)
    return re.sub(r'[,;]\s*$', '', text)


def for_voice(passage):
    """The passage with each sentence made speakable. A sentence of marks alone is kept as
    a short pause so every sentence still has its own place in the recording."""
    sentences = []
    for sentence in passage['sentences']:
        original = sentence['text']
        text = speakable(original)
        if text.endswith(':') and GAP.search(original.rsplit(':', 1)[-1]):
            text = text[:-1] + '.'  # "Termina: ____" is said as a word in a list, not a lead-in
        sentences.append(sentence if text == original else {**sentence, 'text': text or '…'})
    return {**passage, 'sentences': sentences}
