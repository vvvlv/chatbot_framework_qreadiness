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
    <div className={`flex h-screen flex-col bg-white`}>
      <header className="sticky top-0 z-20 bg-skyblue px-6 py-4 shadow-sm">
        <h1 className="text-3xl font-title font-bold text-navy">
          Quantum Readiness Chatbot
        </h1>
        <p className="mt-1 text-sm text-navy font-paragraph">
          Are you quantum ready? Find out now with a 10-minute conversation.
        </p>

        <div className="mt-4 grid grid-cols-3 gap-2">
          {steps.map((step, index) => {
            const isActive = index === activeStep;
            const isDone = index < activeStep;
            const workflowStep = step === "Quantum Competitiveness";
            return (
              <div
                key={step}
                className={`flex rounded-xl border px-3 py-2 transition ${
                  isActive
                    ? `bg-white border-navy ring-1 ring-navy`
                    : isDone ?
                    "border-skyblue ring-0 bg-navy"
                    : "border-skyblue ring-0 bg-white"
                }`}
              >
                <div className="flex flex-col">
                  <div className="mb-2 flex items-center gap-2">
                    <span
                      className={`inline-flex h-5 w-5 items-center justify-center rounded-full text-[11px] font-title font-bold ${
                        isActive ? `bg-navy text-white` : isDone ? `bg-white text-navy` : "bg-slate-400 text-white"
                      }`}
                    >
                      {index + 1}
                    </span>
                    <span className={`text-[11px] font-paragraph font-semibold ${isActive ? "text-navy" : isDone ? "text-white" : "text-slate-400"}`}>
                      {isActive ? "Active" : isDone ? "Done" : "Pending"}
                    </span>
                  </div>
                  <p className={`text-xs font-paragraph ${isActive ? "text-navy" : isDone ? "text-white" : "text-slate-400"}`}>{step}</p>
                </div>
                {workflowStep && (<ToolChrome toolMeta={toolMeta} onCancel={() => send("/cancel", currentQuestion?.prompt_id)} visible={activeStep === 1} />)}
              </div>
            );
          })}
        </div>
      </header>

      {/* Messages */}
      <div className="flex-1 space-y-4 overflow-y-auto px-6 py-5">
        {messages.length === 0 && (
          <div className="h-full flex items-center justify-center">
            <div className="max-w-md rounded-2xl border border-navy bg-skyblue p-8 text-center shadow-xl">
              <p className="text-2xl font-title font-bold text-navy">
                Click below to start a workflow.
              </p>
              <p className="mt-2 font-paragraph text-sm text-navy">
                Start the structured workflow without typing a command.
              </p>
              <button
                type="button"
                disabled={uiState === "streaming"}
                onClick={() => send("assessment")}
                className="mt-6 w-full rounded-xl bg-teal px-6 py-3 text-white font-paragraph hover:bg-teal/80 hover:cursor-pointer disabled:cursor-not-allowed disabled:bg-slate-400"
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
            <div className="max-w-[82%] rounded-2xl bg-skyblue px-4 py-3 text-navy shadow-sm">
              <div className="flex items-center gap-3">
                <span className="relative inline-flex h-2.5 w-2.5">
                  <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-navy opacity-75" />
                  <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-navy" />
                </span>
                <span className="text-sm text-navy">{processingText}</span>
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
      <div className="bg-skyblue px-6 py-4 shadow-sm">
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
