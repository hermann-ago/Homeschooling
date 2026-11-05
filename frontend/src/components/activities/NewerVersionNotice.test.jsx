/* @vitest-environment jsdom */
import { render, screen, fireEvent, waitFor, cleanup } from '@testing-library/react';
import { afterEach, it, expect, vi } from 'vitest';
const api = vi.hoisted(() => ({ state: vi.fn(), replaceScript: vi.fn() }));
vi.mock('../../api/activities', () => ({ activitiesApi: api }));
import { NewerVersionNotice } from './RegistryGuidedLesson';
afterEach(cleanup);
it('switches an open older session to the updated lesson with its current revision', async () => {
  api.state.mockResolvedValue({ revision: 31 });
  api.replaceScript.mockResolvedValue({ session_id: 's2' });
  const onSwitched = vi.fn();
  render(<NewerVersionNotice newer={{ session_id: 's1', updated_guide_id: 'g2' }} onSwitched={onSwitched} />);
  fireEvent.click(screen.getByRole('button', { name: 'Switch to the updated lesson' }));
  await waitFor(() => expect(onSwitched).toHaveBeenCalledWith('s2'));
  expect(api.replaceScript).toHaveBeenCalledWith('s1', expect.objectContaining({ expected_revision: 31, guide_id: 'g2' }));
});
