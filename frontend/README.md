# Quantum Readiness Chatbot - Frontend

Next.js frontend for the Quantum Readiness Chatbot, implementing the SSE event protocol from `app_definition.md`.

## Features

- **SSE Event Streaming**: Handles typed SSE events from backend
- **UI State Machine**: Manages UI state (idle, streaming, tool_active, awaiting_input, error)
- **Tool Chrome**: Progress bar and cancel button for active tools
- **Adaptive Input**: Shows question context when tool is asking
- **Real-time Updates**: Streaming LLM responses with token-by-token updates

## Setup

1. Install dependencies:
```bash
npm install
```

2. Set environment variables (optional):
```bash
# .env.local
NEXT_PUBLIC_API_URL=http://localhost:8000
```

3. Run development server:
```bash
npm run dev
```

The app will be available at `http://localhost:3000`.

## Architecture

The frontend implements the UI state machine from `app_definition.md` Section 13:

- **`useChat` hook**: Handles SSE event streaming and state management
- **`ChatWindow`**: Main chat interface component
- **`MessageBubble`**: Renders chat messages
- **`ToolChrome`**: Shows tool progress and cancel button
- **`ChatInput`**: Input component with question context

## Event Handling

The frontend handles all SSE event types:
- `session_state` - Updates UI mode
- `text_delta` - Streaming tokens
- `text_done` - Finalizes message
- `tool_start` - Shows tool chrome
- `tool_question` - Shows question and awaits input
- `tool_progress` - Updates progress bar
- `tool_complete` - Hides tool chrome
- `error` - Shows error message
