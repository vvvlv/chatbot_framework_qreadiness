/**
 * Custom hook for handling chat with SSE event streaming.
 * 
 * Implements the UI state machine from app_definition.md Section 13.
 */
'use client';

import { useState, useCallback, useRef } from 'react';
import { UIState, SSEEvent, Message, ToolMeta, QuestionEvent, SendOptions, ChatbotKind } from '../types';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export function useChat(sessionId: string) {
  const [uiState, setUIState] = useState<UIState>("idle");
  const [messages, setMessages] = useState<Message[]>([]);
  const [toolMeta, setToolMeta] = useState<ToolMeta | null>(null);
  const [currentQuestion, setCurrentQuestion] = useState<QuestionEvent | null>(null);
  const [recommendedNextChatbot, setRecommendedNextChatbot] = useState<ChatbotKind | null>(null);
  const [completedChatbots, setCompletedChatbots] = useState<ChatbotKind[]>([]);
  const [chatbotSummaries, setChatbotSummaries] = useState<Partial<Record<ChatbotKind, string>>>({});
  const [error, setError] = useState<string | null>(null);
  const [currentResponse, setCurrentResponse] = useState<string>("");
  const abortControllerRef = useRef<AbortController | null>(null);
  const responseBufferRef = useRef<string>("");
  const seenQuestionPromptIdsRef = useRef<Set<string>>(new Set());
  const lastQuestionTextRef = useRef<string | null>(null);

  const handleEvent = useCallback((event: SSEEvent) => {
    if (event.meta?.recommended_next_chatbot !== undefined) {
      setRecommendedNextChatbot((event.meta.recommended_next_chatbot as ChatbotKind | null) ?? null);
    }
    if (event.meta?.completed_chatbots) {
      setCompletedChatbots(event.meta.completed_chatbots as ChatbotKind[]);
    }
    if (event.meta?.chatbot_summaries) {
      setChatbotSummaries(event.meta.chatbot_summaries as Partial<Record<ChatbotKind, string>>);
    }

    switch (event.type) {
      case "session_state":
        if (event.meta.resumable) {
          setUIState("awaiting_input");
        } else if (!event.meta.active_tool) {
          setUIState("idle");
        }
        break;

      case "text_delta":
        setUIState("streaming");
        responseBufferRef.current = responseBufferRef.current + event.payload.token;
        setCurrentResponse(responseBufferRef.current);
        break;

      case "text_done":
        if (responseBufferRef.current || event.payload.full_text) {
          const fullText = event.payload.full_text || responseBufferRef.current;
          setMessages((prev) => [
            ...prev,
            {
              id: Date.now().toString(),
              role: "assistant",
              content: fullText,
              timestamp: new Date(),
            },
          ]);
          responseBufferRef.current = "";
          setCurrentResponse("");
        }
        setUIState("idle");
        break;

      case "tool_start":
        setUIState("tool_active");
        seenQuestionPromptIdsRef.current.clear();
        lastQuestionTextRef.current = null;
        setToolMeta({
          name: event.meta.active_tool || "unknown",
          total: event.meta.tool_total || 0,
          step: 0,
        });
        break;

      case "tool_intro":
        {
          const introText = String(event.payload.text || "").trim();
          const title = String(event.payload.title || "").trim();
          if (introText) {
            setMessages((prev) => [
              ...prev,
              {
                id: `intro-${Date.now()}`,
                role: "assistant",
                content: title ? `## ${title}\n\n${introText}` : introText,
                timestamp: new Date(),
              },
            ]);
          }
        }
        break;

      case "tool_question":
        {
          const questionText = String(event.payload.text || "").trim();
          const promptId = event.payload.prompt_id || event.meta.pending_prompt_id || undefined;
          const alreadySeen =
            (promptId && seenQuestionPromptIdsRef.current.has(promptId)) ||
            (!promptId && lastQuestionTextRef.current === questionText);
          if (questionText && !alreadySeen) {
            setMessages((prev) => [
              ...prev,
              {
                id: promptId ? `q-${promptId}` : `q-${Date.now()}`,
                role: "assistant",
                content: questionText,
                timestamp: new Date(),
              },
            ]);
          }
          if (promptId) {
            seenQuestionPromptIdsRef.current.add(promptId);
          }
          lastQuestionTextRef.current = questionText || null;
        }
        setUIState("awaiting_input");
        setCurrentQuestion({
          text: event.payload.text,
          step: event.payload.step || event.meta.tool_step || 0,
          prompt_id: event.payload.prompt_id || event.meta.pending_prompt_id || undefined,
          input_type: event.payload.input_type || "free_text",
          options: event.payload.options,
          min: event.payload.min,
          max: event.payload.max,
        });
        setToolMeta((prev) => prev ? { ...prev, step: event.payload.step || event.meta.tool_step || 0 } : prev);
        break;

      case "tool_waiting_input":
        setUIState("awaiting_input");
        break;

      case "tool_progress":
        setToolMeta((prev) => prev ? { ...prev, step: event.payload.step } : prev);
        break;

      case "tool_complete":
        setUIState("idle");
        setToolMeta(null);
        setCurrentQuestion(null);
        seenQuestionPromptIdsRef.current.clear();
        lastQuestionTextRef.current = null;
        break;

      case "error":
        setUIState("error");
        setError(event.payload.message || "An error occurred");
        break;

      default:
        console.log("Unknown event type:", event.type);
    }
  }, []);

  const send = useCallback(async (text: string, promptId?: string, options?: SendOptions) => {
    if (!text.trim()) return;

    // Add user message
    const userMessage: Message = {
      id: Date.now().toString(),
      role: "user",
      content: text,
      timestamp: new Date(),
    };
    setMessages((prev) => [...prev, userMessage]);
    setError(null);
    responseBufferRef.current = "";
    setCurrentResponse("");

    // Create abort controller for cancellation
    abortControllerRef.current = new AbortController();

    try {
      const response = await fetch(`${API_URL}/api/chat`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          message: text,
          session_id: sessionId,
          prompt_id: promptId,
          selected_chatbot: options?.selectedChatbot,
          context_message: options?.contextMessage,
        }),
        signal: abortControllerRef.current.signal,
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const reader = response.body?.getReader();
      if (!reader) {
        throw new Error("No response body");
      }

      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || ""; // Keep incomplete line in buffer

        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          
          try {
            const event: SSEEvent = JSON.parse(line.slice(6));
            handleEvent(event);
          } catch (e) {
            console.error("Error parsing SSE event:", e, line);
          }
        }
      }
    } catch (error: any) {
      if (error.name === "AbortError") {
        console.log("Request aborted");
      } else {
        setError(error.message || "Failed to send message");
        setUIState("error");
      }
    } finally {
      abortControllerRef.current = null;
    }
  }, [sessionId, handleEvent]);

  const cancel = useCallback(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    // Send /cancel command
    send("/cancel", currentQuestion?.prompt_id);
  }, [send, currentQuestion]);

  const showSavedSummary = useCallback((summary: string) => {
    if (!summary.trim()) return;
    setMessages((prev) => [
      ...prev,
      {
        id: `summary-${Date.now()}`,
        role: "assistant",
        content: summary,
        timestamp: new Date(),
      },
    ]);
  }, []);

  return {
    uiState,
    messages,
    toolMeta,
    currentQuestion,
    error,
    currentResponse,
    recommendedNextChatbot,
    completedChatbots,
    chatbotSummaries,
    send,
    cancel,
    showSavedSummary,
  };
}
