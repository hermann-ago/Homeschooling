import numpy as np
from tutoring import narration_alignment as a


def test_acoustic_cache_is_bound_to_audio_but_rechecks_every_script(harness,monkeypatch):
    ctx=harness.ctx;calls=[];scripts=[]
    monkeypatch.setattr(a,'_engine',lambda *args:(None,{'a':1}))
    monkeypatch.setattr(a,'_wav',lambda data:(np.zeros(20),1.))
    def emissions(*args):calls.append(1);return np.zeros((3,2)),np.array([.1,.2,.3])
    def coverage(logp,times,sentences,*args):scripts.append(sentences);return {'checked':sentences}
    monkeypatch.setattr(a,'_emissions',emissions)
    monkeypatch.setattr(a,'align_emissions',coverage)
    a.align(ctx,b'synthetic-audio-1',[{'text':'first script'}],'pt-BR')
    a.align(ctx,b'synthetic-audio-1',[{'text':'different script'}],'pt-BR')
    assert len(calls)==1 and len(scripts)==2
    a.align(ctx,b'synthetic-audio-2',[{'text':'first script'}],'pt-BR')
    assert len(calls)==2
    a._emission_path(ctx,b'synthetic-audio-1','pt-BR').write_bytes(b'incomplete cache')
    a.align(ctx,b'synthetic-audio-1',[{'text':'first script'}],'pt-BR')
    assert len(calls)==3
