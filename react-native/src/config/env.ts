const backendUrl =
  process.env.EXPO_PUBLIC_BACKEND_URL ?? "http://localhost:8000";

const deviceToken = process.env.EXPO_PUBLIC_DEVICE_TOKEN ?? "";

export const env = {
  backendUrl,
  deviceToken,
};
