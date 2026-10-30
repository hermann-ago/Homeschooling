"""Planner schemas prevent invalid tool/content pairings before generation."""
import copy

import pytest
from pydantic import ValidationError

from services.ai_provider import strict_schema
from tutoring.activities import ACTIVITY_KINDS, activity_content_model
from tutoring.guide import GuidePlan, ProviderGuidePlan, prompt


def test_every_provider_tool_is_bound_to_its_canonical_content():
    schema = strict_schema(GuidePlan)
    found = {}
    for branch in schema['properties']['segments']['items']['anyOf']:
        model = schema['$defs'][branch['$ref'].rsplit('/', 1)[-1]]
        fields = model['properties']
        if 'activity_kind' in fields:
            found[fields['activity_kind']['const']] = fields['content']['$ref']
    assert set(found) == set(ACTIVITY_KINDS)
    for kind, reference in found.items():
        assert reference == '#/$defs/' + activity_content_model(kind).__name__
    # The planner cannot mint catalog references. These remain supported in
    # canonical saved/session contracts, which receive them from the server.
    for field in ('exercise_id', 'version_id'):
        assert schema['$defs']['SourceRef']['properties'][field] == {'type': 'null'}


def test_visual_tool_round_trips_but_explanation_with_visual_is_not_offered():
    plan = {'mode': 'expand', 'segments': [{'type': 'activity',
        'activity_kind': 'visual_demonstration', 'content': {
            'text': 'Notice the roof shapes.',
            'visual': {'type': 'book_illustration', 'document_id': 1, 'page': 3}}}]}
    prepared = ProviderGuidePlan.model_validate(plan).model_dump(by_alias=True)
    canonical = GuidePlan.model_validate(prepared).model_dump(by_alias=True)
    assert canonical['segments'][0]['content']['visual']['page'] == 3
    invalid = copy.deepcopy(plan)
    invalid['segments'][0]['activity_kind'] = 'explain_or_observe'
    with pytest.raises(ValidationError):
        ProviderGuidePlan.model_validate(invalid)


def test_planner_keeps_server_inserted_exercises_out_of_generated_discussion():
    text = prompt({'title': 'Synthetic rulers', 'sentences': [{'text': 'A city united.'}]},
                  subject='History', learner='Synthetic learner', grade='3', language='en-US')
    assert 'SERVER-INSERTED WORK' in text
    assert 'Do not include, paraphrase or re-create any of these' in text
    assert 'visual_demonstration when content has a visual' in text
    assert 'Preserve substantive footnotes and captions too' in text
    assert 'Do not renumber or rewrite saved sentences' in text
