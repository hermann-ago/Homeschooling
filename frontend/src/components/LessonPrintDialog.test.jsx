/* @vitest-environment jsdom */
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import LessonPrintDialog from './LessonPrintDialog';
afterEach(cleanup);

it('shows book numbers, parity, layout and print order before requesting the system dialog', () => {
  const print = vi.fn(), close = vi.fn();
  render(<LessonPrintDialog first={215} last={219} offset={15} onPrint={print} onClose={close} />);
  expect(screen.getByLabelText('Book pages').value).toBe('200–204');
  fireEvent.change(screen.getByLabelText('Page filter'), { target: { value: 'odd' } });
  fireEvent.change(screen.getByLabelText('Pages per sheet'), { target: { value: '2' } });
  fireEvent.change(screen.getByLabelText('Orientation'), { target: { value: 'landscape' } });
  fireEvent.click(screen.getByLabelText('Reverse page order'));
  expect(within(screen.getByLabelText('Print layout preview')).getByText('Order: 203, 201')).toBeTruthy();
  expect(screen.getByText('2 book pages on 1 sheet')).toBeTruthy();
  expect(print).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button', { name: 'Open print dialog' }));
  expect(print).toHaveBeenCalledWith({ selection: '200–204', parity: 'odd', reverse: true, pagesPerSheet: 2, paper: 'A4', orientation: 'landscape' });
  fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
  expect(close).toHaveBeenCalledTimes(1);
});

it('does not permit an empty filtered selection or pages outside the assigned lesson', () => {
  render(<LessonPrintDialog first={10} last={12} offset={0} onPrint={vi.fn()} onClose={vi.fn()} />);
  fireEvent.change(screen.getByLabelText('Book pages'), { target: { value: '9,10' } });
  expect(screen.getByRole('alert').textContent).toContain('within this lesson');
  expect(screen.getByRole('button', { name: 'Open print dialog' }).disabled).toBe(true);
  fireEvent.change(screen.getByLabelText('Book pages'), { target: { value: '10' } });
  fireEvent.change(screen.getByLabelText('Page filter'), { target: { value: 'odd' } });
  expect(screen.getByRole('alert').textContent).toContain('No odd');
});
