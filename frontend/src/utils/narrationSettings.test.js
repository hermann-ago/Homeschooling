import { expect,it } from 'vitest';
import { narrationVoiceLabel } from './narrationSettings';

it('identifies an imported Inworld narrator in the lesson selector',()=>{
  expect(narrationVoiceLabel({provider:'inworld',voice:'Clive',synchronized:true},true)).toBe('Inworld TTS-2 · Clive');
});
