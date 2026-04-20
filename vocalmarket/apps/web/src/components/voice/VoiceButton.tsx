/**
 * The primary voice button.
 *
 * States:
 *   idle       → grey, tap to start
 *   connecting → spinner
 *   listening  → green pulse, tap to stop
 *   processing → indigo spinner (waiting for AI)
 *   speaking   → indigo pulse (TTS playing)
 *   error      → red, tap to retry
 */

import { useCallback } from "react";
import type { VoiceClientStatus } from "../../lib/voice-client";

interface VoiceButtonProps {
  status: VoiceClientStatus;
  onPressStart: () => void;
  onPressStop: () => void;
  disabled?: boolean;
}

const STATUS_CONFIG: Record<
  VoiceClientStatus,
  { label: string; className: string; animate: boolean }
> = {
  idle: {
    label: "Tap to speak",
    className: "bg-gray-200 hover:bg-gray-300 text-gray-700",
    animate: false,
  },
  connecting: {
    label: "Connecting…",
    className: "bg-gray-200 text-gray-400 cursor-not-allowed",
    animate: true,
  },
  listening: {
    label: "Listening… tap to stop",
    className: "bg-emerald-500 hover:bg-emerald-600 text-white",
    animate: true,
  },
  processing: {
    label: "Processing…",
    className: "bg-indigo-400 text-white cursor-wait",
    animate: true,
  },
  speaking: {
    label: "Speaking…",
    className: "bg-indigo-500 text-white",
    animate: true,
  },
  error: {
    label: "Error — tap to retry",
    className: "bg-red-500 hover:bg-red-600 text-white",
    animate: false,
  },
};

export function VoiceButton({
  status,
  onPressStart,
  onPressStop,
  disabled = false,
}: VoiceButtonProps) {
  const config = STATUS_CONFIG[status];
  const isActive = status === "listening";

  const handleClick = useCallback(() => {
    if (disabled || status === "connecting" || status === "processing") return;
    if (isActive) {
      onPressStop();
    } else {
      onPressStart();
    }
  }, [status, isActive, onPressStart, onPressStop, disabled]);

  return (
    <div className="flex flex-col items-center gap-3">
      <button
        type="button"
        onClick={handleClick}
        disabled={disabled || status === "connecting" || status === "processing"}
        aria-label={config.label}
        className={[
          "relative flex h-20 w-20 items-center justify-center rounded-full",
          "shadow-lg transition-all duration-200 focus:outline-none focus:ring-4",
          "focus:ring-indigo-300 focus:ring-offset-2",
          config.className,
          disabled ? "opacity-50" : "",
        ].join(" ")}
      >
        {/* Pulse ring when listening or speaking */}
        {config.animate && (status === "listening" || status === "speaking") && (
          <span className="absolute inset-0 animate-ping rounded-full bg-current opacity-25" />
        )}

        {/* Microphone icon */}
        {status !== "connecting" && status !== "processing" ? (
          <MicIcon className="h-8 w-8" muted={status === "speaking"} />
        ) : (
          <Spinner className="h-8 w-8" />
        )}
      </button>

      <span className="text-sm text-gray-500">{config.label}</span>
    </div>
  );
}

function MicIcon({ className, muted }: { className: string; muted?: boolean }) {
  return (
    <svg
      className={className}
      fill="currentColor"
      viewBox="0 0 24 24"
      aria-hidden="true"
    >
      {muted ? (
        // Speaker wave icon when AI is speaking
        <path d="M3 9v6h4l5 5V4L7 9H3zm13.5 3c0-1.77-1.02-3.29-2.5-4.03v8.05c1.48-.73 2.5-2.25 2.5-4.02z" />
      ) : (
        // Microphone icon
        <path d="M12 14c1.66 0 3-1.34 3-3V5c0-1.66-1.34-3-3-3S9 3.34 9 5v6c0 1.66 1.34 3 3 3zm-1-9c0-.55.45-1 1-1s1 .45 1 1v6c0 .55-.45 1-1 1s-1-.45-1-1V5zm6 6c0 2.76-2.24 5-5 5s-5-2.24-5-5H5c0 3.53 2.61 6.43 6 6.92V21h2v-3.08c3.39-.49 6-3.39 6-6.92h-2z" />
      )}
    </svg>
  );
}

function Spinner({ className }: { className: string }) {
  return (
    <svg
      className={`${className} animate-spin`}
      xmlns="http://www.w3.org/2000/svg"
      fill="none"
      viewBox="0 0 24 24"
      aria-hidden="true"
    >
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
      <path
        className="opacity-75"
        fill="currentColor"
        d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
      />
    </svg>
  );
}
