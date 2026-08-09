import { createReadStream } from 'node:fs';
import { put } from '@vercel/blob';

const [sourcePath, pathname] = process.argv.slice(2);

if (!sourcePath || !pathname) {
  throw new Error('Usage: node upload_blob.mjs <sourcePath> <pathname>');
}

await put(pathname, createReadStream(sourcePath), {
  access: 'private',
  addRandomSuffix: false,
  allowOverwrite: true,
  contentType: 'application/pdf',
  multipart: true,
});
