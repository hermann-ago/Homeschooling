/* @vitest-environment jsdom */
import {cleanup,fireEvent,render,screen,waitFor} from '@testing-library/react';
import {afterEach,beforeEach,expect,it,vi} from 'vitest';
const api=vi.hoisted(()=>({audioManifest:vi.fn(),audioPart:vi.fn()}));
vi.mock('../api/tutor',()=>({tutorApi:api}));
import LessonAudioReplay from './LessonAudioReplay';

const guide={sentences:[{text:'Welcome.',kind:'teacher'},{text:'Settle in.',kind:'teacher'},
  {text:'Next page task.',kind:'book'},{text:'Tell me your answer.',kind:'teacher'}],
  activities:[{start_sentence:0,end_sentence:1},{start_sentence:2,end_sentence:2},{start_sentence:3,end_sentence:3}],
  audio:[{track_id:'google',provider:'google-gemini',voice:'Achird',status:'ready',synchronized:true}]};
beforeEach(()=>{
  api.audioManifest.mockResolvedValue({timing:'local-alignment',tracks:[
    {startSentence:0,sentenceCount:2,sentenceStarts:[0,1],duration:2},
    {startSentence:2,sentenceCount:1,sentenceStarts:[0],duration:1},
    {startSentence:3,sentenceCount:1,sentenceStarts:[0],duration:1}]});
  api.audioPart.mockResolvedValue('blob:saved-audio');
  vi.spyOn(window.HTMLMediaElement.prototype,'pause').mockImplementation(()=>{});
  vi.spyOn(window.HTMLMediaElement.prototype,'play').mockResolvedValue();
});
afterEach(()=>{cleanup();vi.restoreAllMocks();vi.clearAllMocks();});

it('pauses at each step and waits for explicit continuation without exposing the next task',async()=>{
  const {container}=render(<LessonAudioReplay guide={guide} onClose={vi.fn()}/>);
  await waitFor(()=>expect(container.querySelector('audio')).not.toBeNull());
  expect(screen.getByLabelText('Preview playback').value).toBe('steps');
  expect(screen.queryByText('Next page task.')).toBeNull();
  fireEvent.ended(container.querySelector('audio'));
  expect(screen.getByRole('status').textContent).toContain('Paused');
  expect(api.audioPart.mock.calls).toEqual([['google',0]]);
  fireEvent.click(screen.getByRole('button',{name:'Continue preview'}));
  await waitFor(()=>expect(api.audioPart).toHaveBeenCalledWith('google',1));
  expect(screen.getByText('Next page task.')).toBeTruthy();
  expect(screen.queryByText('Tell me your answer.')).toBeNull();
  fireEvent.loadedMetadata(container.querySelector('audio'));
  expect(window.HTMLMediaElement.prototype.play).toHaveBeenCalled();
  fireEvent.ended(container.querySelector('audio'));
  expect(api.audioPart).not.toHaveBeenCalledWith('google',2);
});

it('only plays through activities after choosing continuous listening explicitly',async()=>{
  const {container}=render(<LessonAudioReplay guide={guide} onClose={vi.fn()}/>);
  fireEvent.change(screen.getByLabelText('Preview playback'),{target:{value:'continuous'}});
  await waitFor(()=>expect(container.querySelector('audio')).not.toBeNull());
  expect(screen.getByText('Tell me your answer.')).toBeTruthy();
  expect(screen.queryByRole('button',{name:'Continue preview'})).toBeNull();
  fireEvent.ended(container.querySelector('audio'));
  await waitFor(()=>expect(api.audioPart).toHaveBeenCalledWith('google',1));
});
