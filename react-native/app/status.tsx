import { useCallback, useEffect, useState } from "react";
import {
  ActivityIndicator,
  SafeAreaView,
  StyleSheet,
  Text,
  View,
} from "react-native";

import { fetchHealth, type HealthStatus } from "../src/api/status";
import { env } from "../src/config/env";
import { maskToken } from "../src/utils/mask";

export default function StatusScreen() {
  const [status, setStatus] = useState<HealthStatus | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const canFetch = env.backendUrl !== "";

  const load = useCallback(async () => {
    if (!canFetch) {
      setError("Set backend URL in .env to query status.");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const data = await fetchHealth();
      setStatus(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load status");
    } finally {
      setLoading(false);
    }
  }, [canFetch]);

  useEffect(() => {
    load().catch(() => {});
  }, [load]);

  return (
    <SafeAreaView style={styles.container}>
      <View style={styles.card}>
        <Text style={styles.title}>Status & Control</Text>
        <Text style={styles.subtitle}>
          Backend health as a starting point. Next: BLE provisioning + Story
          Mode control.
        </Text>

        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Env</Text>
          <Text style={styles.label}>Backend URL</Text>
          <Text style={styles.value}>{env.backendUrl || "Not set"}</Text>
          <Text style={styles.label}>Device token</Text>
          <Text style={styles.value}>
            {env.deviceToken ? maskToken(env.deviceToken) : "Not set"}
          </Text>
        </View>

        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Backend status</Text>
          {loading ? <ActivityIndicator color="#92a0ff" /> : null}
          {error ? <Text style={styles.error}>{error}</Text> : null}
          {!loading && !error && status ? (
            <View style={styles.healthCard}>
              <Text style={styles.healthLine}>database: {status.database}</Text>
              <Text style={styles.healthLine}>storage: {status.storage}</Text>
              <Text style={styles.healthLine}>ollama: {status.ollama}</Text>
            </View>
          ) : null}
        </View>
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: "#0b1021",
    paddingHorizontal: 20,
    paddingTop: 24,
  },
  card: {
    backgroundColor: "#131a33",
    borderRadius: 16,
    padding: 20,
    gap: 10,
    borderWidth: 1,
    borderColor: "#1f294a",
    flex: 1,
  },
  title: {
    color: "#f6f8ff",
    fontSize: 22,
    fontWeight: "700",
  },
  subtitle: {
    color: "#c9d1ff",
    fontSize: 14,
    lineHeight: 20,
  },
  section: {
    marginTop: 12,
    paddingTop: 8,
    borderTopWidth: 1,
    borderTopColor: "#1f294a",
    gap: 6,
  },
  sectionTitle: {
    color: "#f6f8ff",
    fontSize: 16,
    fontWeight: "600",
  },
  label: {
    color: "#9fb0ff",
    fontSize: 12,
  },
  value: {
    color: "#eef2ff",
    fontSize: 14,
  },
  error: {
    color: "#ffb4b4",
    fontSize: 14,
  },
  healthCard: {
    backgroundColor: "#192448",
    borderRadius: 12,
    padding: 12,
    borderWidth: 1,
    borderColor: "#22305b",
    gap: 6,
  },
  healthLine: {
    color: "#d5ddff",
    fontSize: 14,
  },
});
