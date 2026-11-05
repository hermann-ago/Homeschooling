/* @vitest-environment jsdom */
import { render, screen, fireEvent, cleanup } from '@testing-library/react';
import { afterEach, it, expect, vi } from 'vitest';
import { EarlierVersionChoice } from './RegistryGuidedLesson';
afterEach(cleanup);
it('lets the family continue the earlier version or start the updated one', () => {
  const onOpen = vi.fn();
  render(<EarlierVersionChoice earlier={{ session_id: 's1', revision: 4, path: '/lesson?learner=1&topic=2&session=s1' }}
    guide={{ guide_id: 'g2' }} busy={false} closed={false} onOpen={onOpen} />);
  expect(screen.getByRole('link', { name: 'Continue the earlier version' }).getAttribute('href')).toContain('session=s1');
  fireEvent.click(screen.getByRole('button', { name: 'Start the updated lesson' }));
  expect(onOpen).toHaveBeenCalledWith(expect.objectContaining({ expected_revision: 4, guide_id: 'g2' }));
  expect(onOpen.mock.calls[0][0].operation_id).toBeTruthy();
});
