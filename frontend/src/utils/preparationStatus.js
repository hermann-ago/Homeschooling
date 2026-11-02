export const reviewRecovered = status => status?.job?.status === 'paused' && status.job.phase === 'review'
  && status.script_status === 'ready' && status.review?.status === 'approved';
