/* @vitest-environment jsdom */
import { render, screen, fireEvent, waitFor, cleanup } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, beforeEach, it, expect, vi } from 'vitest';
import ExerciseAssignment from './ExerciseAssignment';
const api=vi.hoisted(()=>({exerciseAssignment:vi.fn(),assignExercises:vi.fn(),saveExerciseAssignment:vi.fn()}));
vi.mock('../api/books',()=>({booksApi:api}));
afterEach(cleanup);
beforeEach(()=>vi.clearAllMocks());
const lessons=[{topic_id:1,title:'The Plague'},{topic_id:2,title:'A New Way of Living'}];
function show(){return render(<QueryClientProvider client={new QueryClient({defaultOptions:{queries:{retry:false}}})}><ExerciseAssignment topic={2}/></QueryClientProvider>);}
it('shows nothing when the lesson’s exercise pages are its own',async()=>{
  api.exerciseAssignment.mockResolvedValue({shared:false,lessons:[],pages:[],revision:0,assignment:null});
  const {container}=show();
  await waitFor(()=>expect(api.exerciseAssignment).toHaveBeenCalled());
  expect(container.textContent).toBe('');
});
it('lets a grown-up move an item to another lesson and saves with the revision',async()=>{
  api.exerciseAssignment.mockResolvedValue({shared:true,lessons,pages:[],revision:2,assignment:{method:'ai',items:[
    {label:'9',document_id:5,page:99,topic_id:1},{label:'10',document_id:5,page:99,topic_id:2}]}});
  api.saveExerciseAssignment.mockResolvedValue({});
  show();
  fireEvent.change(await screen.findByLabelText('Lesson for item 9'),{target:{value:'2'}});
  fireEvent.click(screen.getByRole('button',{name:'Save assignment'}));
  await waitFor(()=>expect(api.saveExerciseAssignment).toHaveBeenCalledWith(2,[
    {label:'9',document_id:5,page:99,topic_id:2},{label:'10',document_id:5,page:99,topic_id:2}],2));
});
it('offers to assign items when none are saved yet',async()=>{
  api.exerciseAssignment.mockResolvedValue({shared:true,lessons,pages:[],revision:0,assignment:null});
  api.assignExercises.mockResolvedValue({});
  show();
  fireEvent.click(await screen.findByRole('button',{name:'Assign items now'}));
  await waitFor(()=>expect(api.assignExercises).toHaveBeenCalledWith(2));
});
