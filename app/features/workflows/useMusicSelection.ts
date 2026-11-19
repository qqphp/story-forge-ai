import { useEffect, useRef, useState } from "react";
import { API_BASE } from "@/app/lib/api";
import type { BackgroundMusic } from "@/app/features/shared/types";

export function useMusicSelection(connected: boolean) {
  const [music, setMusic] = useState<BackgroundMusic[]>([]);
  const [musicId, selectMusic] = useState("");
  const [loaded, setLoaded] = useState(false);
  const touched = useRef(false);
  useEffect(() => {
    if (!connected) return;
    const controller = new AbortController();
    fetch(`${API_BASE}/api/background-music?page_size=50`, { signal: controller.signal })
      .then(response => { if (!response.ok) throw new Error(); return response.json(); })
      .then(data => {
        const items: BackgroundMusic[] = data.items;
        const defaultItem: BackgroundMusic | null = data.default_item;
        setMusic(defaultItem && !items.some(item => item.id === defaultItem.id) ? [defaultItem, ...items] : items);
        if (!touched.current) selectMusic(defaultItem?.id || "");
      }).catch(() => {}).finally(() => { if (!controller.signal.aborted) setLoaded(true); });
    return () => controller.abort();
  }, [connected]);
  const setMusicId = (id: string) => { touched.current = true; selectMusic(id); };
  return { music, musicId, setMusicId, musicLoading: connected && !loaded };
}
