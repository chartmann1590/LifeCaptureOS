import { Link } from "expo-router";
import { SafeAreaView, StyleSheet, Text, View, Pressable } from "react-native";

import { env } from "../src/config/env";
import { maskToken } from "../src/utils/mask";

const navItems = [
  {
    href: "/status",
    title: "Device status & control",
    note: "Story mode, BLE, health",
  },
  {
    href: "/gallery",
    title: "Gallery",
    note: "Media list + thumbnails from backend",
  },
  {
    href: "/settings",
    title: "Settings",
    note: "Backend URL, tokens, capture prefs",
  },
];

export default function HomeScreen() {
  return (
    <SafeAreaView style={styles.container}>
      <View style={styles.card}>
        <Text style={styles.overline}>LifeCaptureOS</Text>
        <Text style={styles.title}>React Native + Expo</Text>
        <Text style={styles.subtitle}>
          Cross-platform shell to replace the native Android app. Start in Expo
          Go, wire BLE + backend next.
        </Text>

        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Environment</Text>
          <Text style={styles.label}>Backend URL</Text>
          <Text style={styles.value}>{env.backendUrl}</Text>
          <Text style={styles.label}>Device token</Text>
          <Text style={styles.value}>
            {env.deviceToken ? maskToken(env.deviceToken) : "Not set"}
          </Text>
        </View>

        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Navigate</Text>
          {navItems.map((item) => (
            <Link key={item.href} href={item.href} asChild>
              <Pressable
                style={({ pressed }) => [
                  styles.navButton,
                  pressed && styles.navButtonPressed,
                ]}
              >
                <Text style={styles.navTitle}>{item.title}</Text>
                <Text style={styles.navNote}>{item.note}</Text>
              </Pressable>
            </Link>
          ))}
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
    gap: 8,
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
  navButton: {
    backgroundColor: "#1a2347",
    borderRadius: 12,
    padding: 14,
    borderWidth: 1,
    borderColor: "#22305b",
  },
  navButtonPressed: {
    borderColor: "#3b4f8a",
  },
  navTitle: {
    color: "#f6f8ff",
    fontSize: 15,
    fontWeight: "600",
  },
  navNote: {
    color: "#c9d1ff",
    fontSize: 13,
  },
});
