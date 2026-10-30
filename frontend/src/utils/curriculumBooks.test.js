import { expect, it } from 'vitest';
import { curriculumBooks } from './curriculumBooks';

it('keeps separately imported books with the same filename in their own lesson order',()=>{
  const topics=[
    {id:12,document_id:19,pdf_filename:'Course.pdf',title:'Lesson 61',chapter_order:2,page_start:9,is_core:true,completed:true},
    {id:21,document_id:20,pdf_filename:'Course.pdf',title:'Lesson 1',chapter_order:1,page_start:2,is_core:false},
    {id:11,document_id:19,pdf_filename:'Course.pdf',title:'Lesson 60',chapter_order:1,page_start:4,is_core:true},
    {id:22,document_id:20,pdf_filename:'Course.pdf',title:'Lesson 2',chapter_order:2,page_start:6,is_core:false},
  ];
  const original=structuredClone(topics);
  const books=curriculumBooks(topics);
  expect(books).toHaveLength(2);
  expect(books[0].chapters.map(t=>t.title)).toEqual(['Lesson 60','Lesson 61']);
  expect(books[1].chapters.map(t=>t.title)).toEqual(['Lesson 1','Lesson 2']);
  expect(books.map(b=>b.detail)).toEqual(['Lessons 60–61','Lessons 1–2']);
  expect(books[0].key).not.toBe(books[1].key);
  expect(topics).toEqual(original);
});

it('retains separate legacy printed books and unambiguous PDF labels',()=>{
  const books=curriculumBooks([
    {id:1,title:'First',pdf_filename:'A',chapter_order:0},
    {id:2,title:'Second',pdf_filename:'B',chapter_order:0},
    {id:3,title:'Third',document_id:8,pdf_filename:'Actual.pdf',chapter_order:0},
  ]);
  expect(books.map(b=>b.title)).toEqual(['A','B','Actual']);
  expect(books.every(b=>!b.detail)).toBe(true);
});
