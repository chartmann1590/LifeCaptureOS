type FetchArgs = {
  path: string;
  method?: "GET" | "POST" | "PUT" | "DELETE";
  token?: string;
  body?: Record<string, unknown>;
};

export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

export const createClient = (baseUrl: string) => {
  const normalized = baseUrl?.replace(/\/+$/, "");

  const request = async <T>({
    path,
    method = "GET",
    token,
    body,
  }: FetchArgs): Promise<T> => {
    if (!normalized) throw new ApiError("Backend URL is not set", 400);

    const headers: Record<string, string> = {
      "Content-Type": "application/json",
    };
    if (token) headers.Authorization = `Bearer ${token}`;

    const res = await fetch(`${normalized}${path}`, {
      method,
      headers,
      body: body ? JSON.stringify(body) : undefined,
    });

    if (!res.ok) {
      const message = await safeMessage(res);
      throw new ApiError(
        message ?? `Request failed (${res.status})`,
        res.status,
      );
    }

    return await (res.json() as Promise<T>);
  };

  return { request };
};

const safeMessage = async (res: Response) => {
  try {
    const data = await res.json();
    if (data?.message) return data.message;
  } catch {
    // ignore parse errors
  }
  return "";
};
