import { useCallback, useEffect, useRef, useState } from "react";

export function useAsyncData<T>(fetcher: () => Promise<T>, deps: readonly unknown[] = []) {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const reqIdRef = useRef(0);

  const load = useCallback(async () => {
    const id = ++reqIdRef.current;
    setLoading((prev) => (data === null ? true : prev));
    setError(null);
    try {
      const result = await fetcher();
      if (id === reqIdRef.current) {
        setData(result);
      }
    } catch (err) {
      if (id === reqIdRef.current) {
        setError(err instanceof Error ? err.message : "Failed to load data");
      }
    } finally {
      if (id === reqIdRef.current) {
        setLoading(false);
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  useEffect(() => {
    void load();
  }, [load]);

  return { data, setData, loading, error, reload: load };
}
