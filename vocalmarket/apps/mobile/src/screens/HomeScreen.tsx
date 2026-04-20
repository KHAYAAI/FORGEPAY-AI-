/**
 * Home screen — vertical selector + voice entry point.
 *
 * The prominent voice button is the first thing the user sees.
 * Vertical selection is a swipeable tab strip above the button.
 */

import { Audio } from "expo-av";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  SafeAreaView,
  ScrollView,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from "react-native";
import type { Vertical } from "../../../../shared/types/voice";
import { VoiceButton, type VoiceStatus } from "../components/voice/VoiceButton";

const VERTICALS: Array<{ key: Vertical; label: string; emoji: string }> = [
  { key: "grocery", label: "Grocery", emoji: "🛒" },
  { key: "b2b_procurement", label: "B2B", emoji: "🏭" },
  { key: "healthcare", label: "Health", emoji: "💊" },
];

const WS_BASE = process.env.EXPO_PUBLIC_VOICE_WS_BASE ?? "ws://localhost:8003";

interface Message {
  id: string;
  role: "user" | "assistant";
  text: string;
}

export default function HomeScreen() {
  const [vertical, setVertical] = useState<Vertical>("grocery");
  const [status, setStatus] = useState<VoiceStatus>("idle");
  const [messages, setMessages] = useState<Message[]>([]);
  const [transcript, setTranscript] = useState("");

  const wsRef = useRef<WebSocket | null>(null);
  const recordingRef = useRef<Audio.Recording | null>(null);
  const userId = "user-123"; // In production: from auth store

  useEffect(() => {
    // Request mic permissions on mount
    Audio.requestPermissionsAsync().then(({ status: s }) => {
      if (s !== "granted") setStatus("error");
    });
  }, []);

  // Reconnect WebSocket when vertical changes
  useEffect(() => {
    wsRef.current?.close();
    const ws = new WebSocket(`${WS_BASE}/ws/voice/${vertical}/${userId}`);
    ws.binaryType = "arraybuffer";

    ws.onopen = () => setStatus("idle");
    ws.onerror = () => setStatus("error");
    ws.onmessage = (e) => {
      if (typeof e.data === "string") {
        const msg = JSON.parse(e.data);
        if (msg.type === "transcription") setTranscript(msg.payload?.text ?? "");
        if (msg.type === "agent_response") {
          setTranscript("");
          setStatus("speaking");
          setMessages((prev) => [
            ...prev,
            { id: `ai-${Date.now()}`, role: "assistant", text: msg.payload?.text ?? "" },
          ]);
        }
        if (msg.type === "tts_complete") setStatus("idle");
      }
    };

    wsRef.current = ws;
    return () => ws.close();
  }, [vertical]);

  const handlePressIn = useCallback(async () => {
    if (status !== "idle") return;
    setStatus("listening");

    await Audio.setAudioModeAsync({ allowsRecordingIOS: true, playsInSilentModeIOS: true });
    const { recording } = await Audio.Recording.createAsync(
      Audio.RecordingOptionsPresets.HIGH_QUALITY
    );
    recordingRef.current = recording;
  }, [status]);

  const handlePressOut = useCallback(async () => {
    if (status !== "listening" || !recordingRef.current) return;
    setStatus("processing");

    await recordingRef.current.stopAndUnloadAsync();
    const uri = recordingRef.current.getURI();
    recordingRef.current = null;

    if (uri && wsRef.current?.readyState === WebSocket.OPEN) {
      const response = await fetch(uri);
      const buffer = await response.arrayBuffer();
      wsRef.current.send(buffer);

      // Optimistically add transcript to messages
      if (transcript) {
        setMessages((prev) => [
          ...prev,
          { id: `user-${Date.now()}`, role: "user", text: transcript },
        ]);
      }
    }
  }, [status, transcript]);

  return (
    <SafeAreaView style={styles.container}>
      {/* Vertical selector */}
      <View style={styles.verticalSelector}>
        {VERTICALS.map((v) => (
          <TouchableOpacity
            key={v.key}
            onPress={() => setVertical(v.key)}
            style={[
              styles.verticalTab,
              vertical === v.key && styles.verticalTabActive,
            ]}
            accessibilityRole="tab"
            accessibilityState={{ selected: vertical === v.key }}
          >
            <Text style={styles.verticalEmoji}>{v.emoji}</Text>
            <Text
              style={[
                styles.verticalLabel,
                vertical === v.key && styles.verticalLabelActive,
              ]}
            >
              {v.label}
            </Text>
          </TouchableOpacity>
        ))}
      </View>

      {/* Message history */}
      <ScrollView
        style={styles.messages}
        contentContainerStyle={styles.messagesContent}
      >
        {messages.length === 0 && (
          <Text style={styles.emptyHint}>Hold the mic button and speak</Text>
        )}
        {messages.map((msg) => (
          <View
            key={msg.id}
            style={[
              styles.bubble,
              msg.role === "user" ? styles.bubbleUser : styles.bubbleAI,
            ]}
          >
            <Text
              style={[
                styles.bubbleText,
                msg.role === "user" ? styles.bubbleTextUser : styles.bubbleTextAI,
              ]}
            >
              {msg.text}
            </Text>
          </View>
        ))}
        {transcript.length > 0 && (
          <View style={[styles.bubble, styles.bubbleUser, styles.bubbleLive]}>
            <Text style={[styles.bubbleText, styles.bubbleTextUser]}>{transcript}…</Text>
          </View>
        )}
      </ScrollView>

      {/* Voice button */}
      <View style={styles.voiceArea}>
        <VoiceButton
          status={status}
          onPressIn={handlePressIn}
          onPressOut={handlePressOut}
        />
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#fff" },
  verticalSelector: {
    flexDirection: "row",
    borderBottomWidth: 1,
    borderColor: "#f3f4f6",
    paddingHorizontal: 16,
    paddingVertical: 8,
    gap: 8,
  },
  verticalTab: {
    flex: 1,
    alignItems: "center",
    paddingVertical: 8,
    borderRadius: 12,
    backgroundColor: "#f9fafb",
  },
  verticalTabActive: {
    backgroundColor: "#eef2ff",
  },
  verticalEmoji: { fontSize: 22 },
  verticalLabel: { fontSize: 12, color: "#6b7280", marginTop: 2 },
  verticalLabelActive: { color: "#4f46e5", fontWeight: "600" },
  messages: { flex: 1 },
  messagesContent: {
    padding: 16,
    gap: 12,
    flexGrow: 1,
    justifyContent: "flex-end",
  },
  emptyHint: {
    textAlign: "center",
    color: "#9ca3af",
    fontSize: 14,
    marginTop: 40,
  },
  bubble: {
    maxWidth: "80%",
    borderRadius: 18,
    paddingHorizontal: 14,
    paddingVertical: 10,
  },
  bubbleUser: {
    alignSelf: "flex-end",
    backgroundColor: "#6366f1",
    borderBottomRightRadius: 4,
  },
  bubbleAI: {
    alignSelf: "flex-start",
    backgroundColor: "#f3f4f6",
    borderBottomLeftRadius: 4,
  },
  bubbleLive: { opacity: 0.6 },
  bubbleText: { fontSize: 15, lineHeight: 22 },
  bubbleTextUser: { color: "#fff" },
  bubbleTextAI: { color: "#111827" },
  voiceArea: {
    paddingVertical: 32,
    alignItems: "center",
    borderTopWidth: 1,
    borderColor: "#f3f4f6",
    backgroundColor: "#fff",
  },
});
