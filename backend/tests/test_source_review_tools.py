"""Offline extraction does not certify uninspected source pages."""
import json
import pytest
from tests.pdf_fixture import make_pdf
from tools.book_source_review import draft,checkpoint


def test_draft_and_review_checkpoint_preserve_original_extraction(tmp_path):
    pytest.importorskip('pymupdf')
    pdf=tmp_path/'Original.pdf';pdf.write_bytes(make_pdf([['Original visible wording.']]))
    output=tmp_path/'source.json';draft(pdf,'combined','Synthetic edition',output)
    original=json.loads(output.read_text(encoding='utf8'));page=original['contents']['pages'][0]
    assert page['status']=='native_draft' and not page['student_safe']
    decisions=tmp_path/'decisions.json';body={'source_sha256':original['contents']['source']['sha256'],
        'pages':[{'page':1,'text':'Original visible wording.','status':'checked','review_method':'visual','issues':[],
                  'elements':[],'student_safe':True}]}
    decisions.write_text(json.dumps(body),encoding='utf8');reviewed=tmp_path/'reviewed.json'
    checkpoint(output,decisions,reviewed)
    assert json.loads(reviewed.read_text(encoding='utf8'))['contents']['pages'][0]['native_text']==page['native_text']
    body['pages'][0]['native_text']='Rewritten extraction'
    decisions.write_text(json.dumps(body),encoding='utf8')
    with pytest.raises(ValueError,match='preserve original extraction'):checkpoint(output,decisions,reviewed)
