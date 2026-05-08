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
        <path d="M3 6.75H27M10.5 2.25H19.5M12 21.75V12.75M18 21.75V12.75M20.25 27.75H9.75C8.09315 27.75 6.75 26.4069 6.75 24.75L6.0651 8.31245C6.02959 7.46026 6.71087 6.75 7.5638 6.75H22.4362C23.2891 6.75 23.9704 7.46026 23.9349 8.31245L23.25 24.75C23.25 26.4069 21.9069 27.75 20.25 27.75Z" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
      </svg>
    )
}

export function ChatInput({ onSend, onDelete, disabled, currentQuestion, uiState }: ChatInputProps) {
  const [input, setInput] = useState("");
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

  return (
    <div className="space-y-3">
      {currentQuestion && (
        <div className="flex items-center gap-2 text-xs font-paragraph">
          <span className="inline-flex items-center rounded-full text-navy bg-transparent px-2.5 py-1">
            Awaiting your answer...
          </span>
          <button
            type="button"
            disabled={disabled}
            onClick={() => onSend("/skip", currentQuestion?.prompt_id)}
            className="rounded-full border border-navy px-3 py-1 text-navy hover:bg-navy/10 hover:cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
          >
            Skip
          </button>
          <button
            type="button"
            disabled={disabled}
            onClick={() => onSend("/clarify", currentQuestion?.prompt_id)}
            className="rounded-full border border-teal px-3 py-1 text-teal hover:bg-teal/10 hover:cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
          >
            Clarify
          </button>
          <button
            type="button"
            disabled={disabled}
            onClick={() => onSend("/cancel", currentQuestion?.prompt_id)}
            className="rounded-full border border-darker-beige px-3 py-1 text-darker-beige hover:bg-darker-beige/10 hover:cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
          >
            Cancel
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
          className="flex-1 rounded-xl bg-white px-4 py-3 text-navy placeholder:text-navy/50 focus:outline-none focus:ring-2 focus:ring-navy resize-none"
          style={{ minHeight: "44px", maxHeight: "120px" }}
        />
        <button
          type="button"
          disabled={disabled}
          onClick={onDelete}
          className="rounded-xl bg-white border border-red-500 px-3 py-2 font-paragraph font-medium text-red-500 hover:bg-red-100 hover:cursor-pointer disabled:cursor-not-allowed disabled:border-slate-400 disabled:text-slate-400"
        >
          <TrashIcon />
        </button>
        <button
          type="submit"
          disabled={disabled || !input.trim()}
          className="rounded-xl bg-navy px-6 py-2 font-paragraph font-medium text-white hover:bg-navy/80 hover:cursor-pointer disabled:cursor-not-allowed disabled:bg-slate-400"
        >
          {disabled ? "Sending..." : "Send"}
        </button>
      </form>
    </div>
  );
}
