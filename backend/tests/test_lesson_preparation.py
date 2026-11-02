"""Preparation previews are free and bounded generation shares the family ledger."""
import json

import httpx

from tests.test_tutoring import seed_history
from tests.test_ai_costs import enable_voice, audio_response
from tutoring import passages


def test_saved_warmup_audio_retrieves_server_prompt_and_cached_replay_is_free(harness):
    h = harness; s = seed_history(h); session_id = '2026-09-24-genghis'; sent = []
    with h.ctx.store.transaction() as tx:
        tx.insert('lesson_actions', {'id': session_id + ':warmup', 'session_id': session_id, 'child_id': s['lucas']['id'],
            'subject_id': s['history']['id'], 'topic_id': s['genghis']['id'], 'action_id': 'warmup', 'kind': 'answer',
            'status': 'pending', 'prompt': 'Recall the tribes from our earlier lesson.'})
    enable_voice(h, lambda request: sent.append(json.loads(request.content)) or audio_response())
    url = f'/api/tutor/sessions/{session_id}/action-audio'
    assert h.call('POST', url, json={'action_id': 'invented', 'dry_run': False}).status_code == 400
    ready = h.call('POST', url, json={'action_id': 'warmup', 'text': 'Do not speak this client text.', 'dry_run': False})
    assert ready.status_code == 200, ready.text
    assert sent[0]['input'][0]['content'][0]['text'] == 'Recall the tribes from our earlier lesson.'
    h.config.update(tts={'enabled': False})
    assert h.call('POST', url, json={'action_id': 'warmup', 'dry_run': False}).json()['reused'] and len(sent) == 1
    assert h.call('POST', url, role='tutor', json={'action_id': 'warmup'}).status_code == 403


