/**
 * Custom hook for handling chat with SSE event streaming.
 * 
 * Implements the UI state machine from app_definition.md Section 13.
 */
'use client';

import { useState, useCallback, useRef } from 'react';
import { UIState, SSEEvent, Message, ToolMeta, QuestionEvent } from '../types';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export function useChat(sessionId: string, setSessionId: (value: string) => void) {
  const [uiState, setUIState] = useState<UIState>("idle");
  const [messages, setMessages] = useState<Message[]>([]);
  const [toolMeta, setToolMeta] = useState<ToolMeta | null>(null);
  const [currentQuestion, setCurrentQuestion] = useState<QuestionEvent | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [currentResponse, setCurrentResponse] = useState<string>("");
  const [lockChatInput, setLockChatInput] = useState<boolean>(false);
  const abortControllerRef = useRef<AbortController | null>(null);
  const responseBufferRef = useRef<string>("");
  const seenQuestionPromptIdsRef = useRef<Set<string>>(new Set());
  const lastQuestionTextRef = useRef<string | null>(null);

  const handleEvent = useCallback((event: SSEEvent) => {
    console.log("event received :", event.type);
    switch (event.type) {
      case "session_state":
        // if (event.meta.resumable) {
        //   setUIState("awaiting_input");
        // } else if (!event.meta.active_tool) {
        //   setUIState("idle");
        // }
        break;

      case "text_delta":
        setUIState("streaming");
        responseBufferRef.current = responseBufferRef.current + event.payload.token;
        setCurrentResponse(responseBufferRef.current);
        break;

      case "text_done":
        // enable chat input
        setLockChatInput(false);
        setUIState("idle");
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
        break;

      case "tool_start":
        setUIState("tool_active");
        seenQuestionPromptIdsRef.current.clear();
        lastQuestionTextRef.current = null;
        setToolMeta({
          name: event.payload.tool_name || "unknown",
          total: event.payload.total_steps || 0,
          step: 0,
        });
        break;

      case "tool_question": 
        // enable chat input
        setLockChatInput(false);
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
          prompt_id: event.payload.prompt_id || event.meta.pending_prompt_id || undefined,
          input_type: event.payload.input_type || "free_text",
          options: event.payload.options,
          min: event.payload.min,
          max: event.payload.max,
        });
        break;

      case "tool_waiting_input":
        // enable chat input
        setLockChatInput(false);

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

  const send = useCallback(async (text: string, promptId?: string) => {
    if (!text.trim()) return;

    // disable chat input
    setLockChatInput(true);
    
    // TODO : skip this instruction in case of non-chat request
    setUIState("awaiting_assistant");

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

  const deleteHistory = useCallback(() => {
    // clear history
    setMessages([]);
    setUIState("idle");
    setToolMeta(null);
    setCurrentQuestion(null);
    setCurrentResponse("");
    setLockChatInput(false);

    // clear refs ?
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    if (responseBufferRef.current) {
      responseBufferRef.current = "";
    }
    if (seenQuestionPromptIdsRef.current) {
      seenQuestionPromptIdsRef.current = new Set();
    }
    if (lastQuestionTextRef.current) {
      lastQuestionTextRef.current = null;
    }

    // change sessionId
    const newSessionId = crypto.randomUUID();
    if (typeof window !== 'undefined') {
      localStorage.setItem('session_id', newSessionId);
    }
    setSessionId(newSessionId);
  }, [])

  return {
    uiState,
    messages,
    toolMeta,
    currentQuestion,
    error,
    currentResponse,
    lockChatInput,
    send,
    deleteHistory,
    cancel,
  };
}
