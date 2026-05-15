"""
Fallback LLM node - Layer 1 core node.

Boundary assistant when no subgraph matches the intent.
Not a general-purpose chatbot: redirects users to the readiness workflow.
"""
import re
from typing import List

from core.state import CoreState
from core.model_gateway import ModelGateway

FALLBACK_SYSTEM_PROMPT = """You are the boundary assistant for the Quantum Readiness Chatbot.

You are NOT a general-purpose AI assistant. Do not answer unrelated questions such as coding help, homework, weather, news, recipes, creative writing, personal advice, or open-ended chit-chat.

Your only role:
1. Give a brief, friendly reply (one or two short sentences).
2. Redirect the user to start the Quantum Readiness assessment by clicking the assessment button or typing "assessment".

Keep responses under 60 words. Never present yourself as ChatGPT or a general chatbot."""

GUARDRAIL_REDIRECT_MESSAGE = (
    "I can't help you with that. I'm here to run the Quantum Readiness assessment.\n\n"
    "To begin, click **Quantum Readiness Assessment** or type `assessment` in the chat."
)

ASSESSMENT_HINT_MESSAGE = (
    "It sounds like you want the readiness assessment.\n\n"
    "Click **Quantum Readiness Assessment** or type `assessment` to start the guided workflow."
)


async def fallback_llm_node(state: CoreState, model_gateway: ModelGateway) -> CoreState:
    """
    Redirect off-topic or unmatched input back to the assessment workflow.
    """
    session_id = state.get("session_id", "unknown")
    print(f"[FALLBACK_LLM] Guardrail response for session: {session_id}")

    messages = state.get("messages", [])
    if not messages:
        print("[FALLBACK_LLM] No messages, returning assessment redirect")
        state["output"] = GUARDRAIL_REDIRECT_MESSAGE
        return state

    last_message = messages[-1]
    user_input = last_message.content if hasattr(last_message, "content") else str(last_message)
    user_input = str(user_input or "").strip()
    print(f"[FALLBACK_LLM] User message: {user_input[:100]}...")

    normalized = " ".join(user_input.lower().split())
    if _is_assessment_start_request(normalized):
        state["output"] = ASSESSMENT_HINT_MESSAGE
        return state

    if _is_clearly_off_topic(user_input, normalized):
        print("[FALLBACK_LLM] Off-topic message detected, using guardrail redirect")
        state["output"] = GUARDRAIL_REDIRECT_MESSAGE
        return state

    conversation_context: List[dict] = []
    for msg in messages[-5:]:
        role = "user" if hasattr(msg, "type") and msg.type == "human" else "assistant"
        content = msg.content if hasattr(msg, "content") else str(msg)
        conversation_context.append({"role": role, "content": content})

    llm_messages = [{"role": "system", "content": FALLBACK_SYSTEM_PROMPT}] + conversation_context

    try:
        print(f"[FALLBACK_LLM] Calling LLM with guardrailed prompt ({len(llm_messages)} messages)...")
        response = await model_gateway.chat(
            messages=llm_messages,
            temperature=0.2,
        )
        response = (response or "").strip()
        if not response or _response_looks_like_general_chat(response):
            print("[FALLBACK_LLM] Response failed guardrail check, using default redirect")
            state["output"] = GUARDRAIL_REDIRECT_MESSAGE
        else:
            print(f"[FALLBACK_LLM] Guardrailed response ({len(response)} chars)")
            state["output"] = response
    except Exception as e:
        print(f"[FALLBACK_LLM] Error: {e}")
        import traceback

        traceback.print_exc()
        state["output"] = GUARDRAIL_REDIRECT_MESSAGE

    return state


def _is_assessment_start_request(normalized: str) -> bool:
    triggers = {
        "assessment",
        "quantum readiness",
        "readiness assessment",
        "start assessment",
        "run assessment",
        "quantum assessment",
        "evaluate my quantum readiness",
        "am i quantum ready",
    }
    return any(trigger in normalized for trigger in triggers)


def _is_clearly_off_topic(user_input: str, normalized: str) -> bool:
    if _is_assessment_start_request(normalized):
        return False

    if normalized in {"hi", "hello", "hey", "help", "thanks", "thank you"}:
        return False

    off_topic_patterns = [
        r"\b(write|generate|create)\b.{0,30}\b(code|script|essay|poem|story|email)\b",
        r"\b(python|javascript|java|c\+\+|sql|react|docker)\b",
        r"\b(weather|forecast|temperature)\b",
        r"\b(recipe|cook|ingredients)\b",
        r"\b(who is|what is the capital|when did|tell me about)\b",
        r"\b(joke|horoscope|dating advice|relationship advice)\b",
        r"\b(homework|assignment|solve this math)\b",
        r"\b(translate|summarize this article|news today)\b",
        r"\b(chatgpt|gpt|general ai)\b",
    ]
    if any(re.search(pattern, normalized) for pattern in off_topic_patterns):
        return True

    # Long open-ended prompts are usually general chat, not assessment setup.
    if len(normalized.split()) >= 20 and "quantum" not in normalized and "readiness" not in normalized:
        return True

    return False


def _response_looks_like_general_chat(response: str) -> bool:
    normalized = " ".join(response.lower().split())
    risky_phrases = [
        "here is the code",
        "here's the code",
        "step 1:",
        "as an ai language model",
        "certainly! here's",
        "the weather",
        "recipe",
    ]
    if any(phrase in normalized for phrase in risky_phrases):
        return True
    if "assessment" not in normalized and "quantum" not in normalized and len(normalized.split()) > 80:
        return True
    return False
