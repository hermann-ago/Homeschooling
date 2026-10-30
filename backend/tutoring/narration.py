"""Explicit voice selection, independent of the teaching provider. Never fail over."""
def generate(ctx, topic, passage, *, provider=None, **options):
    selected_provider=provider or ctx.config.get('tts',{}).get('provider','google-gemini')
    if provider is not None and provider not in ('google-gemini','elevenlabs','kokoro-local','inworld'):
        raise ValueError('Choose a supported narration provider')
    if not options.get('dry_run'):
        from .script_review import require_audio
        require_audio(ctx,passage)
    if selected_provider == 'inworld':
        from .inworld_audio import generate as selected
    elif selected_provider == "elevenlabs":
        from .elevenlabs_audio import generate as selected
    elif selected_provider == "kokoro-local":
        from .local_audio import generate as selected
    elif selected_provider=='google-gemini' and options.get('purpose')=='feedback':
        # A short reply has no book highlighting or activity cuts. Preserve its
        # exact recording/cache without running full lesson acoustic alignment.
        from .expressive_audio import generate as selected
    elif ctx.config.get('tts', {}).get('aligned_blocks'):
        from .aligned_audio import generate as selected
    else:
        from .expressive_audio import generate as selected
    from storage import layout
    token = layout.PRIVATE_AUDIO.set(options.get('purpose') == 'feedback')
    try:
        result = selected(ctx, topic, passage, **options)
    finally:
        layout.PRIVATE_AUDIO.reset(token)
    if not options.get('dry_run') and options.get('purpose') != 'feedback' and result.get('track_id'):
        from .library_materials import remember_audio
        remember_audio(ctx, topic, result['track_id'])
    return result
