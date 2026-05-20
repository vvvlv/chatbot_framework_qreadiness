'use client';

import { useState, KeyboardEvent, useEffect, useRef } from 'react';
import { QuestionEvent, UIState } from '../types';

interface ChatInputProps {
  onSend: (text: string, promptId?: string) => void;
  onDelete: () => void;
  disabled: boolean;
  currentQuestion: QuestionEvent | null;
  uiState: UIState;
}

const TrashIcon = () => {
    return (
      <svg xmlns="http://www.w3.org/2000/svg" width="24" viewBox="0 0 30 30" fill="none">
        <path d="M3 6.75H27M10.5 2.25H19.5M12 21.75V12.75M18 21.75V12.75M20.25 27.75H9.75C8.09315 27.75 6.75 26.4069 6.75 24.75L6.0651 8.31245C6.02959 7.46026 6.71087 6.75 7.5638 6.75H22.4362C23.2891 6.75 23.9704 7.46026 23.9349 8.31245L23.25 24.75C23.25 26.4069 21.9069 27.75 20.25 27.75Z" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
      </svg>
    )
}

export function ChatInput({ onSend, onDelete, disabled, currentQuestion, uiState }: ChatInputProps) {
  const [input, setInput] = useState("");
  const [confirmAction, setConfirmAction] = useState<null | "cancel_workflow" | "clear_history">(null);
  const inputRef = useRef<HTMLTextAreaElement | null>(null);

  useEffect(() => {
    if (uiState === "awaiting_input") {
      inputRef.current?.focus();
    }
  }, [uiState, currentQuestion?.prompt_id]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (input.trim() && !disabled) {
      onSend(input.trim(), currentQuestion?.prompt_id);
      setInput("");
    }
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit(e);
    }
  };

  const placeholder = currentQuestion
    ? "Write your answer..."
    : "Type your message...";

  const [showClearMessage, setShowClearMessage] = useState<boolean>(false);
  const isConfirmOpen = confirmAction !== null;

  const confirmTitle =
    confirmAction === "cancel_workflow"
      ? "Cancel current workflow?"
      : "Clear message history?";

  const confirmDescription =
    confirmAction === "cancel_workflow"
      ? "This will stop the current assessment flow and return to normal chat."
      : "This will permanently remove the current conversation history.";

  const confirmButtonLabel =
    confirmAction === "cancel_workflow" ? "Yes, cancel workflow" : "Yes, clear history";

  const handleConfirmAction = () => {
    if (confirmAction === "cancel_workflow") {
      onSend("/cancel", currentQuestion?.prompt_id);
    } else if (confirmAction === "clear_history") {
      onDelete();
    }
    setConfirmAction(null);
  };

  return (
    <div className="space-y-3">
      {currentQuestion && (
        <div className="flex flex-wrap items-center justify-between gap-2 text-xs font-paragraph">
          <div className="flex flex-wrap items-center gap-2">
            <span className="md:inline-flex hidden items-center rounded-full text-navy bg-transparent px-2.5 py-1">
              Awaiting your answer...
            </span>
            <button
              type="button"
              disabled={disabled}
              onClick={() => onSend("/skip", currentQuestion?.prompt_id)}
              className="rounded-full bg-navy px-3 py-1.5 md:py-1 text-[11px] md:text-xs text-white hover:bg-navy/80 hover:cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
            >
              Skip
            </button>
            <button
              type="button"
              disabled={disabled}
              onClick={() => onSend("/clarify", currentQuestion?.prompt_id)}
              className="rounded-full bg-teal px-3 py-1.5 md:py-1 text-[11px] md:text-xs text-white hover:bg-teal/80 hover:cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
            >
              Clarify
            </button>
            <button
              type="button"
              disabled={disabled}
            onClick={() => setConfirmAction("cancel_workflow")}
              className="rounded-full bg-darker-beige px-3 py-1.5 md:py-1 text-[11px] md:text-xs text-white hover:bg-darker-beige/85 hover:cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
            >
              Cancel
            </button>
          </div>
          <button
            type="button"
            disabled={disabled}
            onClick={() => onSend("/aicompletion", currentQuestion?.prompt_id)}
            className="ml-auto rounded-full bg-light-teal px-3 py-1.5 md:py-1 text-[11px] md:text-xs text-white font-semibold hover:bg-light-teal/85 hover:cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
          >
            AI completion
          </button>
        </div>
      )}
      <form onSubmit={handleSubmit} className="flex gap-2">
        <textarea
          ref={inputRef}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={placeholder}
          disabled={disabled}
          rows={1}
          className="flex-1 rounded-xl bg-white md:px-4 md:py-3 px-3 py-2.5 text-sm md:text-base text-navy placeholder:text-navy/50 focus:outline-none focus:ring-2 focus:ring-navy resize-none"
          style={{ minHeight: "44px", maxHeight: "120px" }}
        />
        <button
          type="button"
          disabled={disabled}
          onClick={() => setConfirmAction("clear_history")}
          onMouseEnter={() => setShowClearMessage(true)}
          onMouseLeave={() => setShowClearMessage(false)}
          className="relative rounded-xl bg-white border border-red-500 px-3 py-2.5 md:py-2 font-paragraph text-red-500 hover:bg-red-100 hover:cursor-pointer disabled:cursor-not-allowed disabled:border-slate-400 disabled:text-slate-400"
        >
          {showClearMessage && (
            <span className="absolute rounded-lg px-1 py-1 w-max bg-beige xs:text-xs text-2xs text-teal font-paragraph top-0 -translate-y-full left-1/2 -translate-x-1/2">
              Clear Message History
            </span>
          )}
          <TrashIcon />
        </button>
        <button
          type="submit"
          disabled={disabled || !input.trim()}
          className="rounded-xl bg-navy xs:px-6 px-4 py-2.5 md:py-2 md:text-md xs:text-sm text-sm xs:text-xs font-paragraph text-white hover:bg-navy/80 hover:cursor-pointer disabled:cursor-not-allowed disabled:bg-slate-400"
        >
          {disabled ? "Sending..." : "Send"}
        </button>
      </form>

      {isConfirmOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center px-4">
          <button
            type="button"
            aria-label="Close confirmation popup"
            className="absolute inset-0 bg-slate-950/50"
            onClick={() => setConfirmAction(null)}
          />
          <div className="relative z-10 w-full max-w-sm rounded-2xl bg-skyblue border border-navy/20 shadow-xl p-4 md:p-5">
            <h3 className="font-title font-bold text-navy text-lg md:text-xl">
              {confirmTitle}
            </h3>
            <p className="mt-2 font-paragraph text-teal text-sm">
              {confirmDescription}
            </p>
            <div className="mt-4 flex justify-end gap-2">
              <button
                type="button"
                className="rounded-xl bg-white px-3 py-2 text-navy text-sm font-paragraph hover:bg-slate-100 hover:cursor-pointer"
                onClick={() => setConfirmAction(null)}
              >
                Back
              </button>
              <button
                type="button"
                className="rounded-xl bg-navy px-3 py-2 text-white text-sm font-paragraph hover:bg-navy/80 hover:cursor-pointer"
                onClick={handleConfirmAction}
              >
                {confirmButtonLabel}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
