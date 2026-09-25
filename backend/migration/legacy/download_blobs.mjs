// One-time download of the previous app's private Vercel Blob books.
// Usage: node download_blobs.mjs <blob-list.json> <output folder>   (needs BLOB_READ_WRITE_TOKEN)
import { createWriteStream, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { Readable } from 'node:stream';
import { pipeline } from 'node:stream/promises';
import { get } from '@vercel/blob';

const [listPath, outDir] = process.argv.slice(2);
if (!listPath || !outDir) throw new Error('Usage: node download_blobs.mjs <blob-list.json> <output folder>');
for (const pathname of JSON.parse(readFileSync(listPath, 'utf8'))) {
  const result = await get(pathname, { access: 'private' });
  if (!result || result.statusCode !== 200) {
    console.error(`Missing ${pathname}`);
    continue;
  }
  await pipeline(Readable.fromWeb(result.stream), createWriteStream(join(outDir, pathname.replaceAll('/', '__'))));
  console.log(`Downloaded ${pathname}`);
}
