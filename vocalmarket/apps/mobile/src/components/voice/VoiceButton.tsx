/**
 * Native mobile voice button.
 *
 * Uses expo-av for audio recording and react-native-reanimated for the
 * pulse animation. Sends recorded audio chunks to the voice service
 * via WebSocket (same protocol as the web client).
 */

import { Audio } from "expo-av";
import { useCallback, useEffect, useRef } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";
import Animated, {
  useAnimatedStyle,
  useSharedValue,
  withRepeat,
  withTiming,
} from "react-native-reanimated";

export type VoiceStatus = "idle" | "connecting" | "listening" | "processing" | "speaking" | "error";

interface VoiceButtonProps {
  status: VoiceStatus;
  onPressIn: () => void;
  onPressOut: () => void;
}

const STATUS_COLORS: Record<VoiceStatus, string> = {
  idle: "#e5e7eb",
  connecting: "#e5e7eb",
  listening: "#10b981",
  processing: "#818cf8",
  speaking: "#6366f1",
  error: "#ef4444",
};

const STATUS_LABELS: Record<VoiceStatus, string> = {
  idle: "Hold to speak",
  connecting: "Connecting…",
  listening: "Listening…",
  processing: "Thinking…",
  speaking: "Speaking…",
  error: "Try again",
};

export function VoiceButton({ status, onPressIn, onPressOut }: VoiceButtonProps) {
  const scale = useSharedValue(1);
  const opacity = useSharedValue(0);
  const isAnimating = status === "listening" || status === "speaking";

  useEffect(() => {
    if (isAnimating) {
      scale.value = withRepeat(withTiming(1.3, { duration: 800 }), -1, true);
      opacity.value = withRepeat(withTiming(0.4, { duration: 800 }), -1, true);
    } else {
      scale.value = withTiming(1);
      opacity.value = withTiming(0);
    }
  }, [isAnimating]);

  const pulseStyle = useAnimatedStyle(() => ({
    transform: [{ scale: scale.value }],
    opacity: opacity.value,
  }));

  const color = STATUS_COLORS[status];

  return (
    <View style={styles.container}>
      {/* Animated pulse ring */}
      <Animated.View
        style={[
          styles.pulse,
          { backgroundColor: color },
          pulseStyle,
        ]}
      />

      <Pressable
        onPressIn={onPressIn}
        onPressOut={onPressOut}
        disabled={status === "connecting" || status === "processing"}
        style={({ pressed }) => [
          styles.button,
          { backgroundColor: color },
          pressed && styles.buttonPressed,
        ]}
        accessibilityLabel={STATUS_LABELS[status]}
        accessibilityRole="button"
      >
        <MicIcon status={status} />
      </Pressable>

      <Text style={styles.label}>{STATUS_LABELS[status]}</Text>
    </View>
  );
}

function MicIcon({ status }: { status: VoiceStatus }) {
  // In a real app: use @expo/vector-icons or react-native-svg
  const isActive = status === "listening" || status === "speaking";
  return (
    <View style={[styles.micDot, isActive && styles.micDotActive]} />
  );
}

const styles = StyleSheet.create({
  container: {
    alignItems: "center",
    gap: 12,
  },
  pulse: {
    position: "absolute",
    width: 96,
    height: 96,
    borderRadius: 48,
  },
  button: {
    width: 80,
    height: 80,
    borderRadius: 40,
    alignItems: "center",
    justifyContent: "center",
    shadowColor: "#000",
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.2,
    shadowRadius: 8,
    elevation: 6,
  },
  buttonPressed: {
    transform: [{ scale: 0.95 }],
  },
  micDot: {
    width: 28,
    height: 28,
    borderRadius: 14,
    backgroundColor: "rgba(0,0,0,0.3)",
  },
  micDotActive: {
    backgroundColor: "rgba(255,255,255,0.9)",
  },
  label: {
    fontSize: 13,
    color: "#6b7280",
    marginTop: 4,
  },
});
