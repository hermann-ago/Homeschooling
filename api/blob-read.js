import { issueSignedToken, presignUrl } from '@vercel/blob';
import { createClient } from '@supabase/supabase-js';

export default async function handler(request, response) {
  try {
    const { blobPath } = typeof request.body === 'string' ? JSON.parse(request.body) : request.body;
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
    const validUntil = Date.now() + 5 * 60 * 1000;
    const signedToken = await issueSignedToken({
      pathname: blobPath,
      operations: ['get'],
      validUntil,
    });
    const { presignedUrl } = await presignUrl(signedToken, {
      operation: 'get',
      pathname: blobPath,
      access: 'private',
      validUntil,
    });
    const verification = await fetch(presignedUrl, { method: 'HEAD' });
    console.log(`Private Blob read host=${new URL(presignedUrl).host} status=${verification.status}`);
    if (!verification.ok) {
      throw new Error(`Hosted document is unavailable (${verification.status})`);
    }
    return response.status(200).json({ url: presignedUrl });
  } catch (error) {
    return response.status(500).json({ error: error.message || 'Could not create document URL' });
  }
}
