'use client';

import { useChat } from '../hooks/useChat';
import { MessageBubble } from './MessageBubble';
import { ChatInput } from './ChatInput';
import { ToolChrome } from './ToolChrome';
import { useState, useEffect, useRef } from 'react';

export function ChatWindow() {
  const isUuid = (value: string): boolean => {
    return /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(
      value
    );
  };
  
  let initSessionId : string = crypto.randomUUID();
  if (typeof window !== 'undefined') {
    const stored = localStorage.getItem('session_id');
    if (stored && isUuid(stored)) {
      initSessionId = stored;
    }
    else {
      localStorage.setItem('session_id', initSessionId);
    }
  }
  const [sessionId, setSessionId] = useState<string>(initSessionId);

  const {
    uiState,
    messages,
    toolMeta,
    currentQuestion,
    error,
    lockChatInput,
    currentResponse,
    send,
    deleteHistory,
  } = useChat(sessionId, setSessionId);

  const steps = [
    "Welcome",
    "Quantum Competitiveness",
    "Report",
  ] as const;

  const activeStep = (() => {
    if (messages.length === 0 && !toolMeta) return 0;
    const hasFinalReport = messages.some(
      (m) => m.role === "assistant" && m.content.includes("QUANTUM READINESS REPORT")
    );
    if (!toolMeta) {
      // Avoid flashing "completed" before tool_start arrives.
      return hasFinalReport ? 2 : 1;
    }

    // Analyzer/presenter phases belong to the final report stage.
    if (toolMeta.name === "quantum_analyzer" || toolMeta.name === "quantum_presenter") {
      return 2;
    }

    const currentToolStep = toolMeta?.step ?? 0;
    if (toolMeta) {
      const total = Math.max(1, toolMeta.total || 1);
      if (currentToolStep <= 0) return 1;
      if (currentToolStep <= total) return 1;
    }
    return 1;
  })();

  const theme = [
    {
      shell: "from-slate-950 via-slate-900 to-slate-950",
      accent: "bg-slate-500",
      ring: "ring-slate-600/40",
      text: "text-slate-200",
    },
    {
      shell: "from-indigo-950 via-slate-900 to-slate-950",
      accent: "bg-indigo-500",
      ring: "ring-indigo-600/40",
      text: "text-indigo-200",
    },
    {
      shell: "from-emerald-950 via-slate-900 to-slate-950",
      accent: "bg-emerald-500",
      ring: "ring-emerald-600/40",
      text: "text-emerald-200",
    },
  ][activeStep];

  const showProcessingIndicator =
    uiState === "awaiting_assistant" || (
      Boolean(toolMeta) &&
      uiState === "tool_active" &&
      !currentQuestion &&
      !currentResponse
    );

  const processingText = (() => {
    if (!toolMeta) return "Processing answer...";
    if (toolMeta.name === "quantum_analyzer") return "Analyzing your branch responses...";
    if (toolMeta.name === "quantum_presenter") return "Generating your readiness report...";
    return "Processing answer...";
  })();

  // keep scroll at the bottom of message list
  const bottomRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  return (
    <div className={`flex h-screen flex-col bg-gradient-to-b ${theme.shell} transition-colors duration-500`}>
      <header className="sticky top-0 z-20 border-b border-slate-800/80 bg-slate-950/70 px-6 py-4 backdrop-blur">
        <h1 className="text-2xl font-bold text-white">
          Quantum Readiness Chatbot
        </h1>
        <p className="mt-1 text-sm text-slate-300">
          Assess your company's quantum readiness through a structured conversational workflow
        </p>

        <div className="mt-4 grid grid-cols-3 gap-2">
          {steps.map((step, index) => {
            const isActive = index === activeStep;
            const isDone = index < activeStep;
            return (
              <div
                key={step}
                className={`rounded-xl border px-3 py-2 transition ${
                  isActive
                    ? `border-slate-600 bg-slate-900 ring-1 ${theme.ring}`
                    : "border-slate-800 bg-slate-950/80"
                }`}
              >
                <div className="mb-2 flex items-center gap-2">
                  <span
                    className={`inline-flex h-5 w-5 items-center justify-center rounded-full text-[11px] font-bold ${
                      isActive || isDone ? `${theme.accent} text-white` : "bg-slate-800 text-slate-400"
                    }`}
                  >
                    {index + 1}
                  </span>
                  <span className={`text-[11px] font-semibold ${isActive ? theme.text : "text-slate-400"}`}>
                    {isActive ? "Active" : isDone ? "Done" : "Pending"}
                  </span>
                </div>
                <p className={`text-xs ${isActive ? "text-slate-100" : "text-slate-400"}`}>{step}</p>
              </div>
            );
          })}
        </div>

        <ToolChrome toolMeta={toolMeta} onCancel={() => send("/cancel", currentQuestion?.prompt_id)} visible={activeStep === 1} />
      </header>

      {/* Messages */}
      <div className="flex-1 space-y-4 overflow-y-auto px-6 py-5">
        {messages.length === 0 && (
          <div className="h-full flex items-center justify-center">
            <div className="max-w-md rounded-2xl border border-slate-800 bg-slate-900/80 p-8 text-center shadow-xl">
              <p className="text-lg font-medium text-slate-100">
                Choose an app to start
              </p>
              <p className="mt-2 text-sm text-slate-400">
                Start the structured workflow without typing a command.
              </p>
              <button
                type="button"
                disabled={uiState === "streaming"}
                onClick={() => send("assessment")}
                className="mt-6 w-full rounded-xl bg-indigo-500 px-6 py-3 text-white hover:bg-indigo-400 disabled:cursor-not-allowed disabled:bg-slate-700"
              >
                Start Quantum Readiness Assessment
              </button>
            </div>
          </div>
        )}

        {messages.map((message) => (
          <MessageBubble key={message.id} message={message} />
        ))}

        {showProcessingIndicator && (
          <div className="flex justify-start">
            <div className="max-w-[82%] rounded-2xl border border-slate-700/80 bg-slate-900/90 px-4 py-3 text-slate-100 shadow-sm">
              <div className="flex items-center gap-3">
                <span className="relative inline-flex h-2.5 w-2.5">
                  <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-indigo-400 opacity-75" />
                  <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-indigo-500" />
                </span>
                <span className="text-sm text-slate-200">{processingText}</span>
              </div>
            </div>
          </div>
        )}

        {/* Streaming response */}
        {currentResponse && (
          <MessageBubble
            message={{
              id: "streaming",
              role: "assistant",
              content: currentResponse,
              timestamp: new Date(),
            }}
            isStreaming={true}
          />
        )}

        {/* Error message */}
        {error && (
          <div className="rounded-xl border border-red-900/80 bg-red-950/40 p-4">
            <p className="text-red-200">{error}</p>
          </div>
        )}

        {/* Keep scroll at the bottom */}
        <div ref={bottomRef}></div>
      </div>

      {/* Input */}
      <div className="border-t border-slate-800 bg-slate-950/90 px-6 py-4 backdrop-blur">
        <ChatInput
          onSend={send}
          onDelete={deleteHistory}
          disabled={uiState === "streaming" || lockChatInput}
          currentQuestion={currentQuestion}
          uiState={uiState}
        />
      </div>
    </div>
  );
}
