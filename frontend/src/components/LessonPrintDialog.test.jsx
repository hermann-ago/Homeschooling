/* @vitest-environment jsdom */
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import LessonPrintDialog from './LessonPrintDialog';
afterEach(cleanup);

it('shows sheet-side parity, complete page groups and reverse printing order before printing', () => {
  const print = vi.fn(), close = vi.fn();
  render(<LessonPrintDialog first={215} last={219} offset={15} onPrint={print} onClose={close} />);
  expect(screen.getByLabelText('Book pages').value).toBe('200–204');
  fireEvent.change(screen.getByLabelText('Sides to print'), { target: { value: 'odd' } });
  fireEvent.change(screen.getByLabelText('Pages per sheet'), { target: { value: '2' } });
  fireEvent.change(screen.getByLabelText('Orientation'), { target: { value: 'landscape' } });
  fireEvent.click(screen.getByLabelText('Reverse side order'));
  const preview = within(screen.getByLabelText('Print layout preview'));
  expect(preview.getByText('Front of sheet 2: 204, blank')).toBeTruthy();
  expect(preview.getByText('Front of sheet 1: 200, 201')).toBeTruthy();
  expect(screen.getByText('3 book pages on 2 sheet sides')).toBeTruthy();
  expect(print).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button', { name: 'Open print dialog' }));
  expect(print).toHaveBeenCalledWith({ selection: '200–204', parity: 'odd', reverse: true, pagesPerSheet: 2, paper: 'A4', orientation: 'landscape' });
  fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
  expect(close).toHaveBeenCalledTimes(1);
});

it('rejects out-of-range input but allows even-numbered book pages on a front and its blank back', () => {
  render(<LessonPrintDialog first={10} last={12} offset={0} onPrint={vi.fn()} onClose={vi.fn()} />);
  fireEvent.change(screen.getByLabelText('Book pages'), { target: { value: '9,10' } });
  expect(screen.getByRole('alert').textContent).toContain('within this lesson');
  expect(screen.getByRole('button', { name: 'Open print dialog' }).disabled).toBe(true);
  fireEvent.change(screen.getByLabelText('Book pages'), { target: { value: '10' } });
  fireEvent.change(screen.getByLabelText('Sides to print'), { target: { value: 'odd' } });
  expect(screen.queryByRole('alert')).toBeNull();
  expect(screen.getByText('Front of sheet 1: 10')).toBeTruthy();
  fireEvent.change(screen.getByLabelText('Sides to print'), { target: { value: 'even' } });
  expect(screen.getByText('Back of sheet 1: blank')).toBeTruthy();
  expect(screen.getByText('Includes 1 blank side to keep the paper aligned.')).toBeTruthy();
  expect(screen.getByRole('button', { name: 'Open print dialog' }).disabled).toBe(false);
});
