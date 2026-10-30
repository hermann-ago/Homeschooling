import { beforeEach, expect, it, vi } from 'vitest';
const fetchApi = vi.hoisted(() => vi.fn());
vi.mock('./client', () => ({ fetchApi }));
import { libraryApi } from './library';

beforeEach(() => fetchApi.mockReset());

it('serializes upload bytes once so retries retain the multipart boundary and operation identity', async () => {
  const file = new File(['%PDF-1.4 source'], 'source.pdf', { type: 'application/pdf' });
  await libraryApi.upload('library-02', file, 3);
  const [path, options] = fetchApi.mock.calls[0];
  expect(path).toBe('/library/books/library-02/file');
  expect(options.body).toBeInstanceOf(Blob);
  expect(options.headers['Content-Type']).toContain('multipart/form-data; boundary=');
  const boundary = options.headers['Content-Type'].split('boundary=')[1];
  const encoded = await options.body.text();
  expect(encoded).toContain(`--${boundary}`);
  expect(encoded).toContain('name="expected_revision"\r\n\r\n3');
  expect(encoded).toContain('%PDF-1.4 source');
  expect(await options.body.text()).toBe(encoded);
});

it('rejects unsupported files before any upload request', async () => {
  await expect(libraryApi.upload('library-02', new File(['book'], 'book.epub'), 1)).rejects.toThrow('PDF');
  expect(fetchApi).not.toHaveBeenCalled();
});
