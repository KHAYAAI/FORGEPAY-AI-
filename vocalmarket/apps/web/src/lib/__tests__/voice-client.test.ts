/**
 * Tests for VoiceClient.
 *
 * Uses vi.fn() mocks for WebSocket and MediaRecorder (browser APIs not available in Node).
 */

import { beforeEach, describe, expect, it, vi } from "vitest";
import { VoiceClient, type VoiceClientCallbacks } from "../voice-client";

// ── WebSocket mock ──────────────────────────────────────────────────────────

class MockWebSocket {
  binaryType = "blob";
  onopen: (() => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;
  onmessage: ((e: MessageEvent) => void) | null = null;
  private _listeners: Record<string, Array<(...args: unknown[]) => void>> = {};

  send = vi.fn();
  close = vi.fn();

  addEventListener(type: string, cb: (...args: unknown[]) => void, _opts?: unknown) {
    if (!this._listeners[type]) this._listeners[type] = [];
    this._listeners[type].push(cb);
  }

  simulateOpen() {
    this.onopen?.();
    this._listeners["open"]?.forEach((cb) => cb());
  }

  simulateError() {
    this.onerror?.();
    this._listeners["error"]?.forEach((cb) => cb(new Event("error")));
  }

  simulateMessage(data: unknown) {
    this.onmessage?.({ data } as MessageEvent);
  }

  simulateClose() {
    this.onclose?.();
  }
}

let mockWs: MockWebSocket;

vi.stubGlobal(
  "WebSocket",
  vi.fn().mockImplementation(() => {
    mockWs = new MockWebSocket();
    return mockWs;
  })
);

// ── Helpers ─────────────────────────────────────────────────────────────────

function makeCallbacks(): VoiceClientCallbacks & {
  statusChanges: string[];
  transcriptions: string[];
  responses: unknown[];
  errors: string[];
} {
  const statusChanges: string[] = [];
  const transcriptions: string[] = [];
  const responses: unknown[] = [];
  const errors: string[] = [];

  return {
    statusChanges,
    transcriptions,
    responses,
    errors,
    onStatusChange: (s) => statusChanges.push(s),
    onTranscription: (t) => transcriptions.push(t),
    onAgentResponse: (r) => responses.push(r),
    onError: (e) => errors.push(e),
  };
}

// ── Tests ────────────────────────────────────────────────────────────────────

describe("VoiceClient", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe("connect()", () => {
    it("sets status to connecting then idle on open", async () => {
      const cbs = makeCallbacks();
      const client = new VoiceClient("sess-1", "user-1", "grocery", cbs);

      const connectPromise = client.connect();
      mockWs.simulateOpen();
      await connectPromise;

      expect(cbs.statusChanges).toContain("connecting");
      expect(cbs.statusChanges.at(-1)).toBe("idle");
    });

    it("rejects and sets error status on WS error", async () => {
      const cbs = makeCallbacks();
      const client = new VoiceClient("sess-1", "user-1", "grocery", cbs);

      const connectPromise = client.connect();
      mockWs.simulateError();

      await expect(connectPromise).rejects.toThrow();
      expect(cbs.statusChanges).toContain("error");
    });

    it("builds WS URL with correct vertical and userId", () => {
      const cbs = makeCallbacks();
      new VoiceClient("sess-1", "user-42", "healthcare", cbs).connect();

      expect(WebSocket).toHaveBeenCalledWith(
        expect.stringContaining("/ws/voice/healthcare/user-42")
      );
    });
  });

  describe("message handling", () => {
    async function connectedClient(cbs: VoiceClientCallbacks) {
      const client = new VoiceClient("sess-1", "user-1", "grocery", cbs);
      const p = client.connect();
      mockWs.simulateOpen();
      await p;
      return client;
    }

    it("calls onTranscription for transcription messages", async () => {
      const cbs = makeCallbacks();
      await connectedClient(cbs);

      mockWs.simulateMessage(
        JSON.stringify({ type: "transcription", text: "show me apples" })
      );

      expect(cbs.transcriptions).toContain("show me apples");
    });

    it("calls onAgentResponse for agent_response messages", async () => {
      const cbs = makeCallbacks();
      await connectedClient(cbs);

      const response = {
        type: "agent_response",
        text: "Here are some apples",
        products: [],
        tts_audio: null,
      };
      mockWs.simulateMessage(JSON.stringify(response));

      expect(cbs.responses).toHaveLength(1);
      expect((cbs.responses[0] as { text: string }).text).toBe("Here are some apples");
    });

    it("calls onError for error messages", async () => {
      const cbs = makeCallbacks();
      await connectedClient(cbs);

      mockWs.simulateMessage(
        JSON.stringify({ type: "error", message: "STT failed" })
      );

      expect(cbs.errors).toContain("STT failed");
    });
  });

  describe("disconnect()", () => {
    it("closes the WebSocket", async () => {
      const cbs = makeCallbacks();
      const client = new VoiceClient("sess-1", "user-1", "grocery", cbs);
      const p = client.connect();
      mockWs.simulateOpen();
      await p;

      client.disconnect();
      expect(mockWs.close).toHaveBeenCalled();
    });
  });
});
