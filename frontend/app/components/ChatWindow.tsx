'use client';

import { useChat } from '../hooks/useChat';
import { MessageBubble } from './MessageBubble';
import { ChatInput } from './ChatInput';
import { useState, useEffect } from 'react';
import { ChatbotKind } from '../types';

export function ChatWindow() {
  const isUuid = (value: string): boolean => {
    return /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(
      value
    );
  };

  const [sessionId] = useState(() => {
    // Generate or retrieve session ID
    if (typeof window !== 'undefined') {
      const stored = localStorage.getItem('session_id');
      if (stored && isUuid(stored)) return stored;
      const newId = crypto.randomUUID();
      localStorage.setItem('session_id', newId);
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
    currentResponse,
    recommendedNextChatbot,
    completedChatbots,
    chatbotSummaries,
    send,
    showSavedSummary,
  } = useChat(sessionId);

  const [contextMessage, setContextMessage] = useState("");
  const [selectedStep, setSelectedStep] = useState<number>(0);

  const steps = [
    "Select Chatbot",
    "Quantum Competitiveness",
    "Cryptographic Risk & Security",
    "Roadmap",
    "Final Recap",
  ] as const;

  const hasFinalRecap = messages.some(
    (m) => m.role === "assistant" && m.content.toLowerCase().includes("final recap across the journey")
  );

  useEffect(() => {
    if (hasFinalRecap) {
      // Roadmap completion should move directly to recap.
      setSelectedStep(4);
      return;
    }
    if (!toolMeta?.name) return;
    if (toolMeta.name === "quantum_competitiveness") setSelectedStep(1);
    if (toolMeta.name === "cryptographic_risk_security") setSelectedStep(2);
    if (toolMeta.name === "roadmap_chatbot") setSelectedStep(3);
  }, [toolMeta?.name, hasFinalRecap]);

  const activeStep = selectedStep;

  const themes = [
    {
      shell: "from-slate-950 via-slate-900 to-slate-950",
      accent: "bg-slate-500",
      ring: "ring-slate-600/40",
      text: "text-slate-200",
    },
    {
      shell: "from-violet-950 via-slate-900 to-slate-950",
      accent: "bg-violet-500",
      ring: "ring-violet-600/40",
      text: "text-violet-200",
    },
    {
      shell: "from-cyan-950 via-slate-900 to-slate-950",
      accent: "bg-cyan-500",
      ring: "ring-cyan-600/40",
      text: "text-cyan-200",
    },
    {
      shell: "from-orange-950 via-slate-900 to-slate-950",
      accent: "bg-orange-500",
      ring: "ring-orange-500/40",
      text: "text-orange-200",
    },
    {
      shell: "from-emerald-950 via-slate-900 to-slate-950",
      accent: "bg-emerald-500",
      ring: "ring-emerald-600/40",
      text: "text-emerald-200",
    },
  ];
  const theme = themes[Math.min(activeStep, themes.length - 1)];

  const showProcessingIndicator =
    Boolean(toolMeta) &&
    uiState === "tool_active" &&
    !currentQuestion &&
    !currentResponse;

  const processingText = (() => {
    if (!toolMeta) return "Processing assessment...";
    if (toolMeta.name === "quantum_competitiveness") return "Running competitiveness chatbot...";
    if (toolMeta.name === "cryptographic_risk_security") return "Running cryptographic risk chatbot...";
    if (toolMeta.name === "roadmap_chatbot") return "Running roadmap chatbot...";
    return "Processing assessment...";
  })();

  const startChatbot = (chatbot: ChatbotKind) => {
    const cleaned = contextMessage.trim();
    const label =
      chatbot === "quantum_competitiveness"
        ? "Starting Quantum Competitiveness chatbot"
        : chatbot === "cryptographic_risk_security"
        ? "Starting Cryptographic Risk & Security chatbot"
        : "Starting Roadmap chatbot";
    if (chatbot === "quantum_competitiveness") setSelectedStep(1);
    if (chatbot === "cryptographic_risk_security") setSelectedStep(2);
    if (chatbot === "roadmap_chatbot") setSelectedStep(3);
    send(label, undefined, {
      selectedChatbot: chatbot,
      contextMessage: cleaned || undefined,
    });
  };

  const continueToRecommended = () => {
    if (!recommendedNextChatbot) return;
    startChatbot(recommendedNextChatbot);
  };

  const chatbotLabel = (chatbot: ChatbotKind) => {
    if (chatbot === "quantum_competitiveness") return "Quantum Competitiveness";
    if (chatbot === "cryptographic_risk_security") return "Cryptographic Risk & Security";
    return "Roadmap";
  };

  return (
    <div className={`flex h-screen flex-col bg-gradient-to-b ${theme.shell} transition-colors duration-500`}>
      <header className="sticky top-0 z-20 border-b border-slate-800/80 bg-slate-950/70 px-6 py-4 backdrop-blur">
        <h1 className="text-2xl font-bold text-white">
          Quantum Readiness Chatbot
        </h1>
        <p className="mt-1 text-sm text-slate-300">
          Assess your company's quantum readiness through a structured conversational workflow
        </p>

        <div className="mt-4 grid grid-cols-5 gap-2">
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
      </header>

      {/* Messages */}
      <div className="flex-1 space-y-4 overflow-y-auto px-6 py-5">
        {messages.length === 0 && (
          <div className="h-full flex items-center justify-center">
            <div className="max-w-md rounded-2xl border border-slate-800 bg-slate-900/80 p-8 text-center shadow-xl">
              <p className="text-lg font-medium text-slate-100">Choose a chatbot to start</p>
              <p className="mt-2 text-sm text-slate-400">
                Recommended flow: start with <strong>Quantum Competitiveness</strong>, then continue to
                Cryptographic Risk & Security, and finish with Roadmap. You can still start from any chatbot.
              </p>
              <textarea
                value={contextMessage}
                onChange={(e) => setContextMessage(e.target.value)}
                placeholder="Optional context to prefill this run..."
                className="mt-5 w-full rounded-xl border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100 placeholder:text-slate-500 focus:outline-none focus:ring-2 focus:ring-indigo-500"
                rows={3}
              />
              <div className="mt-4 grid grid-cols-1 gap-2 text-left">
                <button
                  type="button"
                  disabled={uiState === "streaming"}
                  onClick={() => startChatbot("quantum_competitiveness")}
                  className="w-full rounded-xl bg-indigo-500 px-4 py-3 text-white hover:bg-indigo-400 disabled:cursor-not-allowed disabled:bg-slate-700"
                >
                  1) Start Quantum Competitiveness
                </button>
                <button
                  type="button"
                  disabled={uiState === "streaming"}
                  onClick={() => startChatbot("cryptographic_risk_security")}
                  className="w-full rounded-xl bg-cyan-600 px-4 py-3 text-white hover:bg-cyan-500 disabled:cursor-not-allowed disabled:bg-slate-700"
                >
                  2) Start Cryptographic Risk & Security
                </button>
                <button
                  type="button"
                  disabled={uiState === "streaming"}
                  onClick={() => startChatbot("roadmap_chatbot")}
                  className="w-full rounded-xl bg-emerald-600 px-4 py-3 text-white hover:bg-emerald-500 disabled:cursor-not-allowed disabled:bg-slate-700"
                >
                  3) Start Roadmap
                </button>
              </div>
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
      </div>

      {/* Input */}
      <div className="border-t border-slate-800 bg-slate-950/90 px-6 py-4 backdrop-blur">
        {(recommendedNextChatbot || completedChatbots.length > 0) && (
          <div className="mb-3 space-y-2">
            {recommendedNextChatbot && (
              <button
                type="button"
                onClick={continueToRecommended}
                className="rounded-lg bg-emerald-600 px-4 py-2 text-sm text-white hover:bg-emerald-500"
              >
                Continue to next chatbot: {chatbotLabel(recommendedNextChatbot)}
              </button>
            )}
            {completedChatbots.length > 0 && (
              <div className="flex flex-wrap gap-2">
                {completedChatbots.map((chatbot) => (
                  <button
                    key={chatbot}
                    type="button"
                    onClick={() => {
                      const summary = chatbotSummaries[chatbot];
                      if (summary) {
                        showSavedSummary(summary);
                      }
                    }}
                    className="rounded-full border border-slate-600 px-3 py-1 text-xs text-slate-200 hover:bg-slate-800"
                  >
                    Re-open {chatbotLabel(chatbot)} summary
                  </button>
                ))}
              </div>
            )}
          </div>
        )}
        <ChatInput
          onSend={send}
          disabled={uiState === "streaming"}
          currentQuestion={currentQuestion}
          uiState={uiState}
        />
      </div>
    </div>
  );
}
