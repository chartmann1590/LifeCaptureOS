import { StatusBar } from "expo-status-bar";
import { SafeAreaView, StyleSheet, Text, View } from "react-native";

import { env } from "./src/config/env";
import { maskToken } from "./src/utils/mask";

export default function App() {
  return (
    <SafeAreaView style={styles.container}>
      <View style={styles.card}>
        <Text style={styles.overline}>LifeCaptureOS</Text>
        <Text style={styles.title}>React Native + Expo</Text>
        <Text style={styles.subtitle}>
          Cross-platform shell to replace the native Android app.
        </Text>

        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Connected services</Text>
          <Text style={styles.label}>Backend URL</Text>
          <Text style={styles.value}>{env.backendUrl}</Text>
          <Text style={styles.label}>Device token</Text>
          <Text style={styles.value}>
            {env.deviceToken ? maskToken(env.deviceToken) : "Not set"}
          </Text>
        </View>

        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Next steps</Text>
          <Text style={styles.step}>1) Add BLE + provisioning hooks</Text>
          <Text style={styles.step}>2) Wire backend media list + thumbs</Text>
          <Text style={styles.step}>
            3) Build onboarding and status screens with Expo Router
          </Text>
        </View>
      </View>
      <StatusBar style="light" />
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: "#0b1021",
    paddingHorizontal: 20,
    paddingTop: 32,
  },
  card: {
    backgroundColor: "#131a33",
    borderRadius: 16,
    padding: 20,
    gap: 10,
    borderWidth: 1,
    borderColor: "#1f294a",
  },
  overline: {
    color: "#92a0ff",
    fontSize: 12,
    letterSpacing: 1,
    textTransform: "uppercase",
  },
  title: {
    color: "#f6f8ff",
    fontSize: 26,
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
    gap: 4,
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
  step: {
    color: "#d5ddff",
    fontSize: 14,
  },
});
