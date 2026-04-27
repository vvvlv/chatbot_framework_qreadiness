/**
 * Type definitions for SSE event protocol.
 * 
 * According to app_definition.md Section 7, all events follow a typed envelope.
 */

export type UIState = "idle" | "streaming" | "tool_active" | "awaiting_input" | "error";
export type ChatbotKind =
  | "quantum_competitiveness"
  | "cryptographic_risk_security"
  | "roadmap_chatbot";

export interface SSEEvent {
  type: string;
  payload: Record<string, any>;
  meta: {
    session_id: string;
    active_tool: string | null;
    tool_step: number | null;
    tool_total: number | null;
    resumable: boolean;
    can_escape: boolean;
    pending_prompt_id?: string | null;
    recommended_next_chatbot?: ChatbotKind | null;
    completed_chatbots?: ChatbotKind[];
    chatbot_summaries?: Partial<Record<ChatbotKind, string>>;
  };
}

export interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: Date;
}

export interface ToolMeta {
  name: string;
  total: number;
  step: number;
}

export interface QuestionEvent {
  text: string;
  step: number;
  prompt_id?: string;
  input_type: "free_text" | "choice" | "number" | "date" | "confirm";
  options?: string[];
  min?: number;
  max?: number;
}

export interface SendOptions {
  selectedChatbot?: ChatbotKind;
  contextMessage?: string;
}
