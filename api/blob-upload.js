import { handleUpload } from '@vercel/blob/client';
import { createClient } from '@supabase/supabase-js';

const maxBytes = 250 * 1024 * 1024;

async function verifiedUser(request, token) {
  const client = createClient(process.env.SUPABASE_URL, process.env.SUPABASE_PUBLISHABLE_KEY, {
    global: { headers: { Authorization: token } },
  });
  const { data, error } = await client.auth.getUser();
  if (error || !data.user) throw new Error('Unauthorized');
  return data.user;
}

export default async function handler(request, response) {
  try {
    const body = typeof request.body === 'string' ? JSON.parse(request.body) : request.body;
    const result = await handleUpload({
      body,
      request,
      onBeforeGenerateToken: async (_pathname, clientPayload) => {
        const { authorization } = JSON.parse(clientPayload || '{}');
        const user = await verifiedUser(request, authorization);
        return {
          allowedContentTypes: ['application/pdf'],
          maximumSizeInBytes: maxBytes,
          addRandomSuffix: true,
          tokenPayload: JSON.stringify({ userId: user.id }),
        };
      },
      onUploadCompleted: async () => {},
    });
    response.status(200).json(result);
  } catch (error) {
    response.status(error.message === 'Unauthorized' ? 401 : 400).json({ error: error.message || 'Upload could not be authorized' });
  }
}
