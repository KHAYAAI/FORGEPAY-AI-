export type Vertical = "grocery" | "b2b_procurement" | "healthcare";

export interface VoiceSession {
  sessionId: string;
  userId: string;
  vertical: Vertical;
  conversationId: string;
}

export interface TranscriptionResult {
  text: string;
  confidence: number;
  language: string;
}

export interface AgentResponse {
  text: string;
  audioUrl?: string;        // ElevenLabs TTS URL
  products?: ProductResult[];
  actions?: SuggestedAction[];
  conversationId: string;
}

export interface ProductResult {
  id: string;
  name: string;
  price: number;
  currency: string;
  supplierId: string;
  supplierName: string;
  isCurated: boolean;       // Preferred supplier flag
  inStock: boolean;
}

export interface SuggestedAction {
  type: "add_to_cart" | "place_order" | "request_quote" | "book_appointment";
  label: string;
  payload: Record<string, unknown>;
}

export interface WebSocketMessage {
  type: "audio_chunk" | "transcription" | "agent_response" | "error" | "tts_chunk";
  payload: unknown;
  sessionId: string;
}
