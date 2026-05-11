'use client';

import { useChat } from '../hooks/useChat';
import { MessageBubble } from './MessageBubble';
import { ChatInput } from './ChatInput';
import { ToolChrome } from './ToolChrome';
import { useState, useEffect, useRef } from 'react';
import { Feedbacks } from './Feedbacks';

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

  const [userId] = useState(() => {
    // Generate or retrieve session ID
    if (typeof window !== 'undefined') {
      const stored = localStorage.getItem('user_id');
      if (stored && isUuid(stored)) return stored;
      const newId = crypto.randomUUID();
      localStorage.setItem('user_id', newId);
      return newId;
    }
    return crypto.randomUUID();
  });

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
    sendFeedback,
  } = useChat(sessionId, setSessionId);

  const steps = [
    "Welcome",
    "Quantum Readiness",
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

  const showSubSteps = (toolMeta ? toolMeta.name === "quantum_data_collector" : false);

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

  const [showFeedbackPopup, setShowFeedbackPopup] = useState<boolean>(false);

  return (
    <div className={`flex relative h-screen flex-col bg-white`}>
      <header className="sticky top-0 bg-skyblue px-6 py-4 shadow-sm">
        <div className="flex flex-col xs:flex-row-reverse flex-1 xs:justify-between xs:items-center gap-2">
          <div className="flex-1 xs:flex-none flex flex-row justify-between">
            <span
              className="inline-flex xs:hidden items-center justify-center rounded-full aspect-square h-6 py-2 xs:h-0 xs:py-0 text-sm font-title font-bold bg-navy text-white hover:cursor-pointer"
            >
              ?
            </span>
            <button
              type="button"
              onClick={() => {
                setShowFeedbackPopup(true);
              }}
              className="h-max rounded-xl bg-navy px-4 md:px-6 py-2 font-paragraph lg:text-md md:text-sm text-xs text-white hover:bg-navy/80 hover:cursor-pointer disabled:cursor-not-allowed disabled:bg-slate-400"
            >
              Feedback
            </button>
          </div>
          <div className="flex flex-col">
            <div className="flex gap-6 items-center">
              <h1 className="md:text-3xl text-2xl font-title font-bold text-navy">
                Quantum Readiness Chatbot
              </h1>
              <span
                className="hidden xs:inline-flex items-center justify-center rounded-full aspect-square h-0 py-0 xs:h-6 xs:py-2 text-sm font-title font-bold bg-navy text-white hover:cursor-pointer"
              >
                ?
              </span>
            </div>
            <p className="mt-1 md:text-sm text-xs text-teal font-paragraph">
              Are you quantum ready? Find out now with a 10-minute conversation.
            </p>
          </div>
        </div>

        <div className="mt-4 grid grid-cols-3 gap-2">
          {steps.map((step, index) => {
            const isActive = index === activeStep;
            const isDone = index < activeStep;
            const workflowStep = step === "Quantum Readiness";
            return (
              <div
                key={step}
                className={`flex rounded-xl border md:px-3 px-2 py-2 overflow-hidden transition ${
                  isActive
                    ? `bg-white border-navy ring-1 ring-navy`
                    : isDone ?
                    "border-skyblue ring-0 bg-navy"
                    : "border-skyblue ring-0 bg-white"
                }`}
              >
                <div className="flex flex-col overflow-hidden">
                  <div className="mb-2 flex items-center gap-2 overflow-hidden">
                    <span
                      className={`inline-flex h-4 w-4 md:h-5 md:w-5 items-center justify-center rounded-full md:text-[11px] text-[9px] font-title font-bold ${
                        isActive ? `bg-navy text-white` : isDone ? `bg-white text-navy` : "bg-slate-400 text-white"
                      }`}
                    >
                      {index + 1}
                    </span>
                    <span className={`md:text-[11px] text-[9px] truncate font-paragraph font-semibold ${isActive ? "text-navy" : isDone ? "text-white" : "text-slate-400"}`}>
                      {isActive ? "Active" : isDone ? "Done" : "Pending"}
                    </span>
                  </div>
                  <p className={`md:text-xs text-[9px] truncate font-paragraph ${isActive ? "text-navy" : isDone ? "text-white" : "text-slate-400"}`}>{step}</p>
                </div>
                {workflowStep && (
                  <div className="hidden md:block flex-1">
                    <ToolChrome
                      toolMeta={toolMeta}
                      visible={activeStep === 1}
                    />
                  </div>
                )}
              </div>
            );
          })}
        </div>

        {showSubSteps && (
          <div className="md:hidden block md:h-0 flex-1">
            <ToolChrome
              toolMeta={toolMeta}
              visible={activeStep === 1}
            />
          </div>
        )}
      </header>

      {/* Messages */}
      <div className="flex-1 space-y-4 overflow-y-auto xs:px-6 px-4 py-5">
        {messages.length === 0 && (
          <div className="h-full flex items-center justify-center">
            <div className="max-w-md rounded-2xl border border-navy bg-skyblue p-8 text-center shadow-xl">
              <p className="md:text-2xl text-xl font-title font-bold text-navy">
                Click below to start a workflow.
              </p>
              <p className="mt-2 font-paragraph md:text-sm text-xs text-teal">
                Start the structured workflow without typing a command.
              </p>
              <button
                type="button"
                disabled={uiState === "streaming"}
                onClick={() => send("assessment")}
                className="mt-6 w-full rounded-xl bg-teal xs:px-6 px-4 py-3 md:text-md xs:text-sm text-xs text-white font-paragraph hover:bg-teal/80 hover:cursor-pointer disabled:cursor-not-allowed disabled:bg-slate-400"
              >
                Quantum Readiness Assessment
              </button>
            </div>
          </div>
        )}

        {messages.map((message) => (
          <MessageBubble key={message.id} message={message} />
        ))}

        {showProcessingIndicator && (
          <div className="flex justify-start">
            <div className="max-w-[82%] rounded-2xl bg-beige border border-dark-beige text-teal px-4 py-3 shadow-sm">
              <div className="flex items-center gap-3">
                <span className="relative inline-flex h-2.5 w-2.5">
                  <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-navy opacity-75" />
                  <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-navy" />
                </span>
                <span className="text-sm text-teal">{processingText}</span>
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
      <div className="bg-skyblue md:px-6 md:py-4 px-3 py-2 shadow-sm">
        <ChatInput
          onSend={send}
          onDelete={deleteHistory}
          disabled={uiState === "streaming" || lockChatInput}
          currentQuestion={currentQuestion}
          uiState={uiState}
        />
      </div>

      {/* Feedback popup */}
      {showFeedbackPopup && (
        <>
          <div className="absolute bg-slate-950/50 inset-0" onClick={() => setShowFeedbackPopup(false)}></div>
          <Feedbacks onSend={sendFeedback} close={() => setShowFeedbackPopup(false)} user_id={userId}/>
        </>
      )}
    </div>
  );
}
