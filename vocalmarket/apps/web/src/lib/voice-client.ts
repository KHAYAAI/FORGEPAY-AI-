/**
 * Voice WebSocket client.
 *
 * Manages the full voice session lifecycle:
 *   1. Opens WebSocket to the voice service
 *   2. Captures mic audio via MediaRecorder (WebM/Opus)
 *   3. Streams audio chunks to the server
 *   4. Receives transcription confirmations + agent text responses
 *   5. Plays back TTS audio chunks via Web Audio API
 */

import type { AgentResponse, Vertical } from "@/types";

type WebSocketMessage =
  | { type: "transcription"; text: string }
  | { type: "agent_response"; text: string; products?: AgentResponse["products"] }
  | { type: "tts_complete" }
  | { type: "error"; message?: string };

export type VoiceClientStatus =
  | "idle"
  | "connecting"
  | "listening"
  | "processing"
  | "speaking"
  | "error";

export interface VoiceClientCallbacks {
  onStatusChange: (status: VoiceClientStatus) => void;
  onTranscription: (text: string) => void;
  onAgentResponse: (response: AgentResponse) => void;
  onError: (message: string) => void;
}

const WS_BASE =
  import.meta.env.VITE_VOICE_WS_BASE ?? "ws://localhost:8003";
const CHUNK_INTERVAL_MS = 250;

export class VoiceClient {
  private ws: WebSocket | null = null;
  private mediaRecorder: MediaRecorder | null = null;
  private audioContext: AudioContext | null = null;
  private audioQueue: ArrayBuffer[] = [];
  private isPlaying = false;
  private status: VoiceClientStatus = "idle";

  constructor(
    private readonly sessionId: string,
    private readonly userId: string,
    private readonly vertical: Vertical,
    private readonly callbacks: VoiceClientCallbacks
  ) {}

  async connect(): Promise<void> {
    this.setStatus("connecting");

    const url = `${WS_BASE}/ws/voice/${this.vertical}/${this.userId}`;
    this.ws = new WebSocket(url);
    this.ws.binaryType = "arraybuffer";

    this.ws.onopen = () => this.setStatus("idle");
    this.ws.onclose = () => this.setStatus("idle");
    this.ws.onerror = () => {
      this.setStatus("error");
      this.callbacks.onError("WebSocket connection failed");
    };
    this.ws.onmessage = (event) => this.handleMessage(event);

    await new Promise<void>((resolve, reject) => {
      const ws = this.ws!;
      ws.addEventListener("open", () => resolve(), { once: true });
      ws.addEventListener("error", () => reject(new Error("WS connect failed")), {
        once: true,
      });
    });
  }

  async startListening(): Promise<void> {
    if (this.status !== "idle") return;

    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    this.audioContext = new AudioContext();

    this.mediaRecorder = new MediaRecorder(stream, {
      mimeType: "audio/webm;codecs=opus",
      audioBitsPerSecond: 16_000,
    });

    this.mediaRecorder.ondataavailable = (e) => {
      if (e.data.size > 0 && this.ws?.readyState === WebSocket.OPEN) {
        e.data.arrayBuffer().then((buf) => this.ws!.send(buf));
      }
    };

    this.mediaRecorder.start(CHUNK_INTERVAL_MS);
    this.setStatus("listening");
  }

  stopListening(): void {
    this.mediaRecorder?.stop();
    this.mediaRecorder?.stream.getTracks().forEach((t) => t.stop());
    this.mediaRecorder = null;
    if (this.status === "listening") this.setStatus("processing");
  }

  disconnect(): void {
    this.stopListening();
    this.ws?.close();
    this.ws = null;
    this.audioContext?.close();
    this.audioContext = null;
    this.setStatus("idle");
  }

  private handleMessage(event: MessageEvent): void {
    if (event.data instanceof ArrayBuffer) {
      // TTS audio chunk — queue for playback
      this.audioQueue.push(event.data);
      if (!this.isPlaying) this.playNextChunk();
      return;
    }

    const msg: WebSocketMessage = JSON.parse(event.data as string);
    switch (msg.type) {
      case "transcription":
        this.callbacks.onTranscription(msg.text);
        break;
      case "agent_response":
        this.setStatus("speaking");
        this.callbacks.onAgentResponse({ text: msg.text, products: msg.products });
        break;
      case "tts_complete":
        break;
      case "error":
        this.setStatus("error");
        this.callbacks.onError(msg.message ?? "Unknown error");
        break;
    }
  }

  private async playNextChunk(): Promise<void> {
    if (!this.audioContext || this.audioQueue.length === 0) {
      this.isPlaying = false;
      if (this.status === "speaking") this.setStatus("idle");
      return;
    }

    this.isPlaying = true;
    const chunk = this.audioQueue.shift()!;

    try {
      const buffer = await this.audioContext.decodeAudioData(chunk);
      const source = this.audioContext.createBufferSource();
      source.buffer = buffer;
      source.connect(this.audioContext.destination);
      source.onended = () => this.playNextChunk();
      source.start();
    } catch {
      // Skip corrupt chunks
      this.playNextChunk();
    }
  }

  private setStatus(status: VoiceClientStatus): void {
    this.status = status;
    this.callbacks.onStatusChange(status);
  }

  get currentStatus(): VoiceClientStatus {
    return this.status;
  }
}
