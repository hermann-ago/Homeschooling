import { useQuery } from '@tanstack/react-query';
import { fetchApi } from './client';
import { currentMode } from './mode';

export const curriculumPrepApi = {
  lesson:(learner,topic)=>fetchApi(`/tutor/preparation/lesson?${new URLSearchParams({learner,topic})}`),
  statuses:(learner,subject,ids)=>fetchApi(`/tutor/preparation?${new URLSearchParams([
    ['learner',learner],['subject',subject],...ids.map(id=>['topic_ids',id])])}`),
  estimate:body=>fetchApi('/tutor/preparation/estimate',{method:'POST',body:JSON.stringify(body)}),
  start:body=>fetchApi('/tutor/preparation',{method:'POST',body:JSON.stringify(body)}),
};

export function useCurriculumPreparation(learner,subject,topics) {
  const ids=topics.map(t=>t.id);
  const query=useQuery({queryKey:['curriculum-preparation',currentMode,learner,subject,ids],
    enabled:ids.length>0,queryFn:async()=>{
      const lessons=[];
      for(let first=0;first<ids.length;first+=200) lessons.push(...(await curriculumPrepApi.statuses(learner,subject,ids.slice(first,first+200))).lessons);
      return {lessons};
    },refetchInterval:query=>query.state.data?.lessons.some(s=>['queued','running'].includes(s.job?.status)||['queued','running','aligning'].includes(s.audio?.status))?3000:30000});
  return {...query,statuses:new Map((query.data?.lessons||[]).map(s=>[s.topic_id,s]))};
}
