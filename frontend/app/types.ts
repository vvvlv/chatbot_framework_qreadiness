/**
 * Type definitions for SSE event protocol.
 * 
 * According to app_definition.md Section 7, all events follow a typed envelope.
 */

export type UIState = "idle" | "streaming" | "tool_active" | "awaiting_input" | "error" | "awaiting_assistant";

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
  prompt_id?: string;
  input_type: "free_text" | "choice" | "number" | "date" | "confirm";
  options?: string[];
  min?: number;
  max?: number;
}

export interface Feedback {
  user_id: string;
  title: string;
  output: number | string;
}

export interface CollectedDataSection {
  title: string;
  content: string;
}

export interface ReportDownloadData {
  reportText: string;
  companyName: string;
  collectedData: CollectedDataSection[];
}