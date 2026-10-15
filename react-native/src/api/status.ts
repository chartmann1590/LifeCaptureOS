import { createClient } from "./client";
import { env } from "../config/env";

export type HealthStatus = {
  database?: string;
  storage?: string;
  ollama?: string;
};

export const fetchHealth = async (): Promise<HealthStatus> => {
  const client = createClient(env.backendUrl);
  return await client.request<HealthStatus>({ path: "/health" });
};
