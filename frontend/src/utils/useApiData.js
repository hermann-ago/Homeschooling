import { useState, useEffect, useCallback } from 'react';

/**
 * Custom hook for API data fetching with loading and error states.
 * 
 * Usage:
 *   const { data, loading, error, refetch } = useApiData(
 *     () => progressApi.getChildProgress(childId),
 *     [childId]
 *   );
 */
export function useApiData(fetchFn, deps = []) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const refetch = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await fetchFn();
      setData(result);
    } catch (err) {
      setError(err);
      console.error('API fetch error:', err);
    } finally {
      setLoading(false);
    }
  }, deps);

  useEffect(() => {
    refetch();
  }, [refetch]);

  return { data, loading, error, refetch };
}
