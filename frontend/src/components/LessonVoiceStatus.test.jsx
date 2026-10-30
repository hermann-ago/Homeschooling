/* @vitest-environment jsdom */
import React from 'react';
import {render,screen,cleanup} from '@testing-library/react';
import {afterEach,it,expect} from 'vitest';
import LessonVoiceStatus from './LessonVoiceStatus';

it('shows the complete preferred recording despite a different provider failure and old text-only audio',()=>{
  render(<LessonVoiceStatus guide={{voice_preparation:{provider:'elevenlabs',status:'paused',error:'Old provider failed'},audio:[
    {provider:'google-gemini',synchronized:true,status:'ready',fallback_parts:20},
    {provider:'inworld',preferred:true,synchronized:true,status:'ready',fallback_parts:0},
  ]}}/>);
  expect(screen.getByText('Inworld voice ready')).toBeTruthy();
  expect(screen.queryByText(/some passages text-only/)).toBeNull();
  expect(screen.queryByText('Old provider failed')).toBeNull();
});
afterEach(cleanup);

it('keeps the workspace notice compact and leaves generation in the preparation bar', () => {
  const { rerender } = render(<LessonVoiceStatus compact learner={1} topic={1688} guide={{
    voice_preparation: { provider: 'elevenlabs', status: 'paused', error: 'A previous request stopped.' }, audio: [] }} />);
  expect(screen.getByText('ElevenLabs voice preparation paused')).toBeTruthy();
  expect(screen.queryByRole('button', { name: 'Retry ElevenLabs voice' })).toBeNull();
  expect(screen.queryByText(/You can continue with text or Device voice/)).toBeNull();
  rerender(<LessonVoiceStatus compact guide={{ voice_preparation: { provider: 'elevenlabs', status: 'ready' }, audio: [] }} />);
  expect(screen.queryByRole('status', { name: 'Lesson voice preparation' })).toBeNull();
});

it('does not claim recordings exist when Google declined every block',()=>{
  render(<LessonVoiceStatus guide={{audio:[],voice_preparation:{provider:'google-gemini',status:'ready_with_fallback',
    recorded_parts:0,parts:2,completed_parts:2,alignment:'local'}}}/>);
  expect(screen.getByText('Google voice declined · no audio saved')).toBeTruthy();
  expect(screen.getByText('0 of 2 audio blocks recorded')).toBeTruthy();
  expect(screen.queryByText(/Saved recordings are available/)).toBeNull();
  expect(screen.queryByText(/2 synchronized/)).toBeNull();
});

it('offers the selected ElevenLabs provider when a saved narration job needs resuming', () => {
  render(<LessonVoiceStatus learner={1} topic={376} guide={{voice_preparation:{provider:'elevenlabs',status:'paused'}}}/>);
  expect(screen.getByText('ElevenLabs voice preparation paused')).toBeTruthy();
  expect(screen.getByRole('button', {name:'Retry ElevenLabs voice'})).toBeTruthy();
  expect(screen.queryByRole('button', {name:'Retry Google voice'})).toBeNull();
});

it('offers one explicit missing-audio retry and removes it after reconsideration',()=>{
  const props={learner:1,topic:375,guide:{voice_preparation:{provider:'google-gemini',status:'ready_with_fallback'}}};
  const {rerender}=render(<LessonVoiceStatus {...props}/>);
  expect(screen.getByRole('button',{name:'Retry missing Google audio'})).toBeTruthy();
  rerender(<LessonVoiceStatus {...props} guide={{voice_preparation:{...props.guide.voice_preparation,missing_retry_used:true}}}/>);
  expect(screen.queryByRole('button',{name:'Retry missing Google audio'})).toBeNull();
});

it('keeps background preparation and synchronization distinct, then shows ready',()=>{
  const props={provider:'google-gemini',parts:3,completed_parts:0,recorded_parts:1,alignment:'local'};
  const {rerender}=render(<LessonVoiceStatus guide={{voice_preparation:{...props,status:'running'}}}/>);
  expect(screen.getByText('Preparing Google voice…')).toBeTruthy();
  expect(screen.getByText('1 of 3 audio blocks saved · 0 synchronized')).toBeTruthy();
  rerender(<LessonVoiceStatus guide={{voice_preparation:{...props,status:'aligning'}}}/>);
  expect(screen.getByText('Synchronizing Google voice…')).toBeTruthy();
  rerender(<LessonVoiceStatus guide={{voice_preparation:{...props,status:'ready',completed_parts:3,recorded_parts:3}}}/>);
  expect(screen.getByText('Google voice ready')).toBeTruthy();
  expect(screen.queryByText(/Working in the background/)).toBeNull();
});

it('shows a paused timing review independently of device-voice playback',()=>{
  render(<LessonVoiceStatus guide={{audio:[],voice_preparation:{provider:'google-gemini',status:'alignment_review',
    error:'Sentence 21 has uncertain acoustic alignment.',parts:3,completed_parts:0,recorded_parts:1,alignment:'local'}}}/>);
  expect(screen.getByRole('status',{name:'Lesson voice preparation'})).toBeTruthy();
  expect(screen.getByText('Google voice paused · synchronization needs attention')).toBeTruthy();
  expect(screen.getByText(/saved audio is kept/)).toBeTruthy();
  expect(screen.getByText(/continue with Device voice/)).toBeTruthy();
});

it('does not claim background work has started when no job exists',()=>{
  render(<LessonVoiceStatus guide={{audio:[]}}/>);
  expect(screen.getByText('Recorded lesson voice has not started')).toBeTruthy();
});

it('offers retry directly in the paused notice for an open lesson',()=>{
  const props={guide:{voice_preparation:{provider:'google-gemini',status:'alignment_review'}},learner:1,topic:1251,session:'pinned'};
  const {rerender}=render(<LessonVoiceStatus {...props}/>);
  expect(screen.getByRole('button',{name:'Retry Google voice'})).toBeTruthy();
  rerender(<LessonVoiceStatus {...props} closed/>);
  expect(screen.queryByRole('button',{name:'Retry Google voice'})).toBeNull();
});
