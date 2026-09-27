import { describe, expect, it } from 'vitest';
import { contrast, learnerTones } from './colors';

describe('learnerTones', () => {
  it('darkens pastel family colours until they read as text on white', () => {
    for (const color of ['#E88AB5', '#7BC67E', '#F5A623', '#4A90D9']) {
      const { strong } = learnerTones(color);
      expect(contrast(strong, '#ffffff')).toBeGreaterThanOrEqual(4.5);
    }
  });

  it('keeps a colour that already passes', () => {
    expect(learnerTones('#1E2226').strong).toBe('#1e2226');
  });

  it('makes a light fill that dark text stays readable on', () => {
    const { soft } = learnerTones('#4A90D9');
    expect(contrast('#1E2226', soft)).toBeGreaterThanOrEqual(7);
  });
});
