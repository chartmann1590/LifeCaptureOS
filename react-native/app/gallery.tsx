import { useCallback, useEffect, useState } from "react";
import {
  ActivityIndicator,
  FlatList,
  Image,
  Pressable,
  RefreshControl,
  SafeAreaView,
  StyleSheet,
  Text,
  View,
} from "react-native";

import { fetchMedia, type MediaItem } from "../src/api/gallery";
import { env } from "../src/config/env";

export default function GalleryScreen() {
  const [items, setItems] = useState<MediaItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const canFetch = env.backendUrl && env.deviceToken;

  const load = useCallback(async () => {
    if (!canFetch) {
      setError("Set backend URL and device token in .env to fetch media.");
      return;
    }

    setLoading(true);
    setError(null);
    try {
      const media = await fetchMedia();
      setItems(media);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to fetch media");
    } finally {
      setLoading(false);
    }
  }, [canFetch]);

  useEffect(() => {
    load().catch(() => {});
  }, [load]);

  const renderItem = ({ item }: { item: MediaItem }) => (
    <View style={styles.listItem}>
      <View style={styles.thumbWrap}>
        {item.thumb_url ? (
          <Image source={{ uri: item.thumb_url }} style={styles.thumb} />
        ) : (
          <View style={styles.thumbPlaceholder}>
            <Text style={styles.thumbPlaceholderText}>No thumb</Text>
          </View>
        )}
      </View>
      <View style={styles.meta}>
        <Text style={styles.metaTitle}>{item.id}</Text>
        {item.caption ? (
          <Text style={styles.metaCaption}>{item.caption}</Text>
        ) : null}
        {item.created_at ? (
          <Text style={styles.metaMeta}>{item.created_at}</Text>
        ) : null}
      </View>
    </View>
  );

  return (
    <SafeAreaView style={styles.container}>
      <View style={styles.card}>
        <Text style={styles.title}>Gallery</Text>
        <Text style={styles.subtitle}>Backend media list with thumbnails.</Text>

        {error ? <Text style={styles.error}>{error}</Text> : null}
        {error ? (
          <Pressable
            style={styles.retry}
            onPress={() => load().catch(() => {})}
          >
            <Text style={styles.retryText}>Retry</Text>
          </Pressable>
        ) : null}
        {loading && items.length === 0 ? (
          <ActivityIndicator color="#92a0ff" />
        ) : null}
        {!loading && !error && items.length === 0 ? (
          <Text style={styles.empty}>No media found.</Text>
        ) : null}

        <FlatList
          data={items}
          keyExtractor={(item) => item.id}
          renderItem={renderItem}
          contentContainerStyle={styles.list}
          refreshControl={
            <RefreshControl
              refreshing={loading}
              onRefresh={load}
              tintColor="#92a0ff"
            />
          }
        />
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
  error: {
    color: "#ffb4b4",
    fontSize: 14,
    marginTop: 4,
  },
  empty: {
    color: "#c9d1ff",
    fontSize: 14,
    marginTop: 8,
  },
  retry: {
    alignSelf: "flex-start",
    backgroundColor: "#1f2d55",
    paddingVertical: 6,
    paddingHorizontal: 12,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: "#304276",
  },
  retryText: {
    color: "#f6f8ff",
    fontWeight: "600",
  },
  list: {
    paddingTop: 8,
    gap: 10,
  },
  listItem: {
    flexDirection: "row",
    gap: 12,
    backgroundColor: "#192448",
    borderRadius: 12,
    padding: 12,
    borderWidth: 1,
    borderColor: "#22305b",
  },
  thumbWrap: {
    width: 80,
    height: 80,
    borderRadius: 10,
    overflow: "hidden",
    backgroundColor: "#0b1021",
    borderWidth: 1,
    borderColor: "#22305b",
    alignItems: "center",
    justifyContent: "center",
  },
  thumb: {
    width: "100%",
    height: "100%",
    resizeMode: "cover",
  },
  thumbPlaceholder: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
  },
  thumbPlaceholderText: {
    color: "#9fb0ff",
    fontSize: 12,
  },
  meta: {
    flex: 1,
    gap: 4,
  },
  metaTitle: {
    color: "#f6f8ff",
    fontSize: 15,
    fontWeight: "600",
  },
  metaCaption: {
    color: "#d5ddff",
    fontSize: 13,
  },
  metaMeta: {
    color: "#9fb0ff",
    fontSize: 12,
  },
});
