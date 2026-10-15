import { createClient } from "./client";
import { env } from "../config/env";

export type MediaItem = {
  id: string;
  device_id?: string;
  created_at?: string;
  thumb_url?: string;
  file_url?: string;
  caption?: string;
};

type MediaResponse = {
  items: MediaItem[];
};

export const fetchMedia = async (): Promise<MediaItem[]> => {
  const client = createClient(env.backendUrl);
  const data = await client.request<MediaResponse>({
    path: "/media",
    token: env.deviceToken,
  });
  return data.items ?? [];
};
