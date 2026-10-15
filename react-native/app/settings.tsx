import { SafeAreaView, StyleSheet, Text, View } from "react-native";

import { env } from "../src/config/env";
import { maskToken } from "../src/utils/mask";

export default function SettingsScreen() {
  return (
    <SafeAreaView style={styles.container}>
      <View style={styles.card}>
        <Text style={styles.title}>Settings</Text>
        <Text style={styles.subtitle}>
          Configure backend URL and device token via `.env`. Capture preferences
          will land here once we map the BLE settings API.
        </Text>

        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Current env</Text>
          <Text style={styles.label}>Backend URL</Text>
          <Text style={styles.value}>{env.backendUrl}</Text>
          <Text style={styles.label}>Device token</Text>
          <Text style={styles.value}>
            {env.deviceToken ? maskToken(env.deviceToken) : "Not set"}
          </Text>
        </View>

        <View style={styles.section}>
          <Text style={styles.sectionTitle}>How to set</Text>
          <Text style={styles.item}>- Copy `.env.example` to `.env`</Text>
          <Text style={styles.item}>- Set `EXPO_PUBLIC_BACKEND_URL`</Text>
          <Text style={styles.item}>- Set `EXPO_PUBLIC_DEVICE_TOKEN`</Text>
          <Text style={styles.item}>
            - Restart `npm start` so Expo picks up changes
          </Text>
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
  item: {
    color: "#d5ddff",
    fontSize: 14,
  },
  label: {
    color: "#9fb0ff",
    fontSize: 12,
  },
  value: {
    color: "#eef2ff",
    fontSize: 14,
  },
});
