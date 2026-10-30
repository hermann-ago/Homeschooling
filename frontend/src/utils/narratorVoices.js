const words = value => String(value || '').replaceAll('_', ' ').replace(/\b\w/g, letter => letter.toUpperCase());

export const voiceLabel = voice => [voice.name, ...['accent', 'gender', 'descriptive'].map(key => words(voice.labels?.[key])).filter(Boolean)].join(' · ');
