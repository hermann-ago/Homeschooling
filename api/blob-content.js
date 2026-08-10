import { get } from '@vercel/blob';
import { createClient } from '@supabase/supabase-js';
import { Readable } from 'node:stream';

export default async function handler(request, response) {
  try {
    const requestUrl = new URL(request.url, 'http://localhost');
    const blobPath = requestUrl.searchParams.get('blobPath');
    const authorization = request.headers.authorization;
    if (!authorization || !blobPath || !/^documents\/[A-Za-z0-9._/-]+$/.test(blobPath)) {
      return response.status(400).json({ error: 'Invalid document request' });
    }

    const client = createClient(process.env.SUPABASE_URL, process.env.SUPABASE_PUBLISHABLE_KEY, {
      global: { headers: { Authorization: authorization } },
    });
    const { data, error } = await client.auth.getUser();
    if (error || !data.user) return response.status(401).json({ error: 'Unauthorized' });

    const origin = process.env.VERCEL_URL ? `https://${process.env.VERCEL_URL}` : new URL(request.url, 'http://localhost').origin;
    const ownership = await fetch(`${origin}/api/documents/by-path/lookup?blob_path=${encodeURIComponent(blobPath)}`, {
      headers: { Authorization: authorization },
    });
    if (!ownership.ok) return response.status(404).json({ error: 'Document not found' });

    const result = await get(blobPath, { access: 'private' });
    if (!result || result.statusCode !== 200) return response.status(404).json({ error: 'Document not found' });

    response.setHeader('Content-Type', result.blob.contentType || 'application/pdf');
    response.setHeader('X-Content-Type-Options', 'nosniff');
    Readable.fromWeb(result.stream).pipe(response);
  } catch (error) {
    return response.status(500).json({ error: error.message || 'Could not load document' });
  }
}
