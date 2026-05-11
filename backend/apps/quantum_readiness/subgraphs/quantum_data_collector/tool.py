"""
Quantum Readiness Data Collection Tool - Layer 3.

OLD LOGIC (field-filling tool):
- A small, fixed set of field specs (key + explanation + default question).
- For each field, ask a question via interrupt().
- On resume, an LLM (mistral small) evaluates if the response is satisfactory for the field,
  rewrites it if needed, and proposes a follow-up question if not satisfactory.
- The user can skip any question (UI sends "/skip") -> we store null/"no_response".
- If the user asks for clarification, we respond with a clarification message and re-ask.

For testing, we collect 4 topic-level fields focused on quantum competitiveness.

NEW IDEA :
- Give a system prompt with all fields and rules at the beginning of data collection.
- Then let the AI manage the discussion (but provide it some field information status)
- After every human message, ask the AI how much information they identified and extract information
- Update field information status
- Frontend : top-sub-bar with status for each field
"""

import json
import uuid
from typing import Any, Dict, List, Optional, TypedDict
from langchain_core.callbacks.manager import adispatch_custom_event
from langgraph.graph import END, START, StateGraph

from core.model_gateway import ModelGateway
from core.protocols import SubgraphProtocol, ToolProtocol
from core.state import SubgraphState

class FieldSpec(TypedDict):
    key: str
    explanation: str
    default_question: str
    answer_criteria: str
    example_answers: List[str]

class QuantumDataCollectorState(TypedDict, total=False):
    """stepData for the field-filling collector."""
    
    messages: list[Dict]
    field_status: Dict[str, str] # field_key -> "empty" | "in_progress" | "complete"
    last_user_answer: Optional[str]
    message_count: int # number of AI + user messages
    iterations_count: Dict[str, int]  # field_key -> number of AI questions on the field
    field_information: Dict[str, str] # field_key -> user information about the field
    user_command: Optional[str] # potential inputed command between /cancel, /skip and /clarify
    current_field_key: Optional[str]
    pending_question: Optional[str]
    consumed_prompt_ids: List[str]
    last_validation_reason: Optional[str]
    step: int

class QuantumDataCollectorTool(SubgraphProtocol):
    """
    Data Collection Tool for Quantum Readiness assessment.
    
    Collects information for Branch A (quantum competitiveness) only.
    
    Uses interrupt() for each question to suspend execution and wait for user response.
    """
    
    # --- Global variables ---

    name = "quantum_data_collector"
    VALIDATOR_MODEL = "claude-sonnet-4-6" # Keep model lightweight for faster validation loops.
    FIELD_SPECS: List[FieldSpec] = [
        {
            "key": "a_use_case_identification",
            "explanation": "Branch A topic: use case identification (industry, computationally intensive problems, optimization, intrinsic quantum use cases, classical bottlenecks).",
            "default_question": "Quantum Competitiveness - Use Case Identification: Tell us your industry and the most computationally intensive problems where quantum could matter, including optimization or intrinsic quantum research, and any current classical bottlenecks.",
            "answer_criteria": "Provide industry context plus at least one concrete high-compute or quantum-relevant use case.",
            "example_answers": ["Healthcare: drug discovery simulation and route optimization with long runtimes.", "Finance: portfolio optimization bottlenecks in intraday decisions."],
        },
        {
            "key": "a_technical_infrastructure_baseline",
            "explanation": "Branch A topic: technical and infrastructure baseline (HPC/cloud footprint, classical baselines, vendor relationships, internal expertise).",
            "default_question": "Quantum Competitiveness - Technical & Infrastructure Baseline: Summarize your compute footprint, classical solution maturity, any quantum vendor relationships, and whether you have internal quantum expertise.",
            "answer_criteria": "Describe current technical baseline and capability level across infrastructure, tooling, and expertise.",
            "example_answers": [
                "Hybrid HPC + cloud, mature classical optimizers, early vendor pilots, small internal team.",
                "Cloud-only stack, no vendor ties, external partners required for quantum work.",
            ],
        },
        {
            "key": "a_strategic_organizational_maturity",
            "explanation": "Branch A topic: strategic and organizational maturity (adoption posture, IP sensitivity, dedicated budget).",
            "default_question": "Quantum Competitiveness - Strategic & Organizational Maturity: Describe your technology adoption posture, IP sensitivity, and whether budget for quantum exploration is dedicated or competing with other initiatives.",
            "answer_criteria": "Provide posture, governance/budget context, and strategic readiness indicators.",
            "example_answers": [
                "Second-mover posture, strong IP portfolio, dedicated exploration budget.",
                "Wait-and-see posture, limited IP pressure, no dedicated budget.",
            ],
        },
        {
            "key": "a_roadmap_ecosystem",
            "explanation": "Branch A topic: roadmap and ecosystem (internal pilots, ecosystem participation, competitor monitoring).",
            "default_question": "Quantum Competitiveness - Roadmap & Ecosystem: Describe any internal quantum assessments/pilots, ecosystem or academic partnerships, and how you track competitor activity.",
            "answer_criteria": "Include execution roadmap signals and ecosystem engagement level.",
            "example_answers": [
                "Active pilots, consortium membership, and quarterly competitor intelligence.",
                "No pilots yet, limited ecosystem ties, informal monitoring only.",
            ],
        },
    ]
    SYSTEM_PROMPT = f"""
SYSTEM PROMPT : 
You are a professional quantum assistant that helps managers to assess the quantum readiness of their company/structure.
Your first step is to gather the information necessary for this assessment.
More precisely, your goal is to identify the user's information according to 4 fields, described by the following attributes :
- "key" : a string to identify the field
- "explanation": an explanation of the field
- "default question": an exemple question to ask to get more information about the field
- "answer_criteria": what information is needed to consider the field as complete
- "example_answers": a list of example user answers that fill the information needed for the field

Here are the 4 fields :

{json.dumps(FIELD_SPECS)}

I will update you on the information status for each field after every user message, and tell you what is the current field to focus on.
Your main objective is always to get more information from the user about the current field, but you can help them to better understand technical terms if they need.
"""
    TOTAL_STEPS = 4
    MAX_RETRIES_PER_FIELD = 5

    # --- Main functions ---

    def __init__(self, model_gateway: ModelGateway, interrupt_tool: ToolProtocol):
        self._model_gateway = model_gateway
        self._interrupt_tool = interrupt_tool
    
    def describe(self) -> str:
        return "Collects structured information for quantum readiness assessment through conversational questioning."
    
    def build(self):
        """Build the field-filling collector tool graph."""

        g = StateGraph(SubgraphState)

        g.add_node("init_state", self.init_node)
        g.add_node("generate_question", self.generate_question_node)
        g.add_node("interrupt", self._interrupt_tool.build())
        g.add_node("process_answer", self.process_answer_node)
        g.add_node("command_handler", self.command_handler_node)
        g.add_node("get_information", self.get_information_node)
        g.add_node("before_analyzer", self.before_analyzer_node)

        g.add_edge(START, "init_state")
        g.add_edge("init_state", "generate_question")
        g.add_edge("generate_question", "interrupt")
        g.add_edge("interrupt", "process_answer")
        g.add_conditional_edges("process_answer", self.router, {
            "command_handler": "command_handler",
            "get_information": "get_information",
            "generate_question": "generate_question"
        })
        g.add_conditional_edges("command_handler", self.router, {
            END: END,
            "before_analyzer": "before_analyzer",
            "generate_question": "generate_question"
        })
        g.add_conditional_edges("get_information", self.router, {
            "before_analyzer": "before_analyzer",
            "generate_question": "generate_question"
        })
        g.add_edge("before_analyzer", END)
        
        return g.compile()
    
    async def router(self, state: SubgraphState) -> str:
        # TODO: manage errors + manage undefined nextNode
        print("[ROUTER]: debug nextNode : ", state.get("nextNode"))
        return state.get("nextNode")
    
    # --- Node functions ---

    async def init_node(self, state: SubgraphState) -> SubgraphState:

        # Convert 5 last BaseMessages to a suitable type for litellm
        last_5_messages = []
        for msg in state.get("messages", [])[-5:]:
            role = "user" if hasattr(msg, 'type') and msg.type == "human" else "assistant"
            content = msg.content if hasattr(msg, 'content') else str(msg)
            last_5_messages.append({"role": role, "content": content})
        
        stepData : QuantumDataCollectorState = {
            "messages": last_5_messages,
            "field_status": {field["key"]: "empty" for field in self.FIELD_SPECS},
            "last_user_answer": None,
            "message_count": 0,
            "iterations_count": {field["key"]: 0 for field in self.FIELD_SPECS},
            "field_information": {field["key"]: "" for field in self.FIELD_SPECS},
            "consumed_prompt_ids": [],
            "last_validation_reason": None,
            "pending_question": None,
            "user_command": None,
            "current_field_key": "a_use_case_identification",
            "step": 1,
        }

        state["currentStep"] = "collecting"
        state["nextNode"] = "generate_question"
        state["stepData"] = stepData
        state["error"] = None
        state["pending_prompt_id"] = None
        state["common_tool_output"] = None
        state["common_tool_input"] = None

        await adispatch_custom_event(
            "tool_start",
            {
                "tool_name": self.name,
                "total_steps": self.TOTAL_STEPS,
                "system_prompt": self.SYSTEM_PROMPT,
                "skip_command": "/skip",
                "clarify_command": "/clarify",
            },
        )
        return state
    
    async def generate_question_node(self, state: SubgraphState) -> SubgraphState:
        prompt_id = state.get("pending_prompt_id") or str(uuid.uuid4())
        state["pending_prompt_id"] = prompt_id
        if state["stepData"].get("pending_question") != None:
            question = state["stepData"]["pending_question"]
            print(f"[DATA_COLLECTOR] DEBUG - pending question : {question}")
        else:
            information_status = self._write_information_status(state["stepData"])
            extra_rules = ""
            if state["stepData"]["iterations_count"][state['stepData']['current_field_key']] == 4:
                extra_rules = """It is your last question to get information about the current field.
If the user strays too far from the topic, warn them that you're going to switch to a next field at next question.
"""
            if state["stepData"].get("last_user_answer", None) == None:
                system_message = f"""
INFORMATION STATUS :

{information_status}

CURRENT FIELD KEY : {state['stepData'].get('current_field_key', 'No current field key')}

INSTRUCTION : generate a question to get more information from the user about the current field.
"""
            else:
                system_message = f"""
INFORMATION STATUS :

{information_status}

CURRENT FIELD KEY : {state['stepData'].get('current_field_key', 'No current field key')}

INSTRUCTION : Generate a message based on your system prompt, the last user message and the message history.
{extra_rules}
"""
            new_message = {
                "role": "user",
                "content": f"""<instructions>{system_message}</instructions>

<user_message>{state['stepData'].get('last_user_answer', 'no user message')}</user_message>"""
            }
            state["stepData"]["messages"].append(new_message)
            llm_message : list[Dict] = [{"role": "system", "content": self.SYSTEM_PROMPT}] + state["stepData"]["messages"][-5:]
            question = await self._model_gateway.chat(
                messages=llm_message,
                model=self.VALIDATOR_MODEL,
                temperature=0.4,
            )
            question = (question or "").strip()
            state["stepData"]["messages"].append({"role": "assistant", "content": question})
            state["stepData"]["pending_question"] = question
            state["stepData"]["message_count"] += 1

        print(f"[DATA_COLLECTOR] DEBUG - used question : {question}")
        state["common_tool_input"] = {
            "nextNode": "process_answer",
            "args": {
                "event_name": "tool_question",
                "text": question,
                "prompt_id": prompt_id,
                "input_type": "free_text",
                "can_skip": True,
            }
        }
        state["nextNode"] = "interrupt"
        return state

    async def process_answer_node(self, state: SubgraphState) -> SubgraphState:
        resume_prompt_id = None
        prompt_id = state.get("pending_prompt_id")
        answer = state["common_tool_output"].get("answer")
        state["stepData"]["message_count"] += 1
        if isinstance(answer, dict):
            raw_answer = str(answer.get("text", "")).strip()
            resume_prompt_id = answer.get("prompt_id")
        else:
            raw_answer = str(answer or "").strip()
        state["stepData"]["last_user_answer"] = raw_answer
        if resume_prompt_id and resume_prompt_id != prompt_id:
            print(f"[DATA_COLLECTOR] DEBUG - Stale prompt answer received.")
            state["stepData"]["last_validation_reason"] = "Stale prompt answer received."
            state["nextNode"] = "generate_question"
            return state
        if prompt_id in state["stepData"]["consumed_prompt_ids"]:
            print(f"[DATA_COLLECTOR] DEBUG - Stale prompt answer received.")
            state["stepData"]["last_validation_reason"] = "Duplicate prompt answer ignored."
            state["nextNode"] = "generate_question"
            return state
        state["stepData"]["pending_question"] = None
        state["stepData"]["consumed_prompt_ids"].append(prompt_id)

        command = self._normalized_command(raw_answer)
        if (command == None):
            state["nextNode"] = "get_information"
        else:
            state["nextNode"] = "command_handler"
            state["stepData"]["user_command"] = command
        return state
    
    async def command_handler_node(self, state: SubgraphState) -> SubgraphState:

        command = state["stepData"].get("user_command")
        field_key = state["stepData"].get("current_field_key")

        if command == "/cancel":
            state["error"] = "Tool cancelled by user."
            state["output"] = "Understood. The conversation has been ended. If you'd like to start a new session or need any assistance, don't hesitate to reach out."
            state["currentStep"] = "Idle"
            state["stepData"] = {}
            state["common_tool_input"] = {}
            state["common_tool_output"] = {}
            state["pending_prompt_id"] = None
            await adispatch_custom_event("tool_complete", {"tool_name": self.name}) # TODO : change args of dispatched event
            state["nextNode"] = END
            return state
        
        if command == "/skip":
            state["stepData"]["field_status"][field_key] = "complete"
            state["stepData"]["field_information"][field_key] += "The user skipped aditional data collection for this field."
            next_field, step = self._next_unfilled_key(state["stepData"]["field_status"])
            state["pending_prompt_id"] = None
            state["stepData"]["last_user_answer"] = None
            if next_field == None:
                await adispatch_custom_event("tool_progress", {"step": self.TOTAL_STEPS, "total": self.TOTAL_STEPS}) # TODO : change args of dispatched event
                state["nextNode"] = "before_analyzer"
                return state
            state["stepData"]["current_field_key"] = next_field
            state["stepData"]["step"] = step
            state["nextNode"] = "generate_question"
            await adispatch_custom_event("tool_progress", {"step": step, "total": self.TOTAL_STEPS}) # TODO : change args of dispatched event
            return state
        
        # Clarification request -> generate clarification message and re-ask.
        if command == "/clarify":
            state["pending_prompt_id"] = None
            state["stepData"]["last_user_answer"] = "Can you clarify your last message ?"
            state["stepData"]["iterations_count"][field_key] += 1
            state["nextNode"] = "generate_question"
            return state
        
    async def get_information_node(self, state: SubgraphState) -> SubgraphState:
        # - extract information about current field
        # - update field status (empty -> partially filled -> complete)
        # - update other fields information/status if relevant
        # - update current field if it has been completed
        # - update iteration count

        current_field = state['stepData']['current_field_key']
        information_status = self._write_information_status(state["stepData"])
        main_prompt = f"""
Your task now is to extract relevant information from the user answer in order to fill the 4 quantum readiness fields described in your system prompt.

Here is a summary of the information already extracted for each field :

{information_status}

The field currently being discussed in the conversation is : {current_field}

Your last message was : {state['stepData']['messages'][-1]["content"]}

The user answered : {state['stepData']['last_user_answer']}
"""
        
        # Task 1
        task1_prompt = "Extract relevant information for the current field from the user answer, based on the current field attributes. If there is no relevant information, just return 'no information'. Do not include markdown, code fences, or extra keys."
        step_messages = [
            {"role": "user", "content": self.SYSTEM_PROMPT},
            {"role": "user", "content": main_prompt},
            {"role": "user", "content": task1_prompt}
        ]
        raw = await self._model_gateway.chat(
            messages=step_messages,
            model=self.VALIDATOR_MODEL,
            temperature=0.2,
        )
        text = (raw or "").strip()
        print(f"[DATA_COLLECTOR] DEBUG - Output task 1 : {text}")

        # Task 2
        task2_prompt = f"""Merge the information you found ({text}) with the already extracted information of the current field ({state['stepData']['field_information'][current_field]}) into a single text summary.
Do not include markdown, code fences, or extra keys.
"""
        step_messages += [
            {"role": "assistant", "content": text},
            {"role": "user", "content": task2_prompt}
        ]
        raw = await self._model_gateway.chat(
            messages=step_messages,
            model=self.VALIDATOR_MODEL,
            temperature=0.2,
        )
        text = (raw or "").strip()
        print(f"[DATA_COLLECTOR] DEBUG - Output task 2 : {text}")
        state["stepData"]["field_information"][current_field] = text

        # Task 3
        output3_format = {
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "enum": ["empty", "in_progress", "complete"]
                }
            }
        }
        task3_prompt = f"""Based on the new information summary for the current field and the answer criteria of the current field,
indicate wether the current field is 'empty' (no user information extracted for this field), 'in_progress' (some user information but not enough) or 'complete' (there is enough user information for this field).
Output STRICT JSON with this schema:
{output3_format}
"""
        step_messages += [
            {"role": "assistant", "content": text},
            {"role": "user", "content": task3_prompt}
        ]
        raw = await self._model_gateway.chat(
            messages=step_messages,
            model=self.VALIDATOR_MODEL,
            temperature=0.1,
        )
        text = (raw or "").strip()
        print(f"[DATA_COLLECTOR] DEBUG - Output task 3 : {text}")
        try:
            start = text.find("{")
            end = text.rfind("}") + 1
            data = json.loads(text[start:end])
            status = data.get("status")
            if status and (status == "complete" or (status == "in_progress" and state["stepData"]["field_status"][current_field] != "complete")):
                state["stepData"]["field_status"][current_field] = status
                state["stepData"]["iterations_count"][current_field] += 1
                if state["stepData"]["iterations_count"][current_field] >= self.MAX_RETRIES_PER_FIELD:
                    state["stepData"]["field_status"][current_field] = "complete"
        except Exception:
            # Fail-safe: treat as incomplete
            print("[DATA_COLLECTOR] DEBUG - Parsing of task 3 output has failed.")
            state["stepData"]["iterations_count"][current_field] += 1
            if state["stepData"]["iterations_count"][current_field] >= self.MAX_RETRIES_PER_FIELD:
                state["stepData"]["field_status"][current_field] = "complete"
        
        # Task 4
        output4_format = {
            "type": "object",
            "properties": {
                "list": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "key": {
                                "type": "string"
                            },
                            "new_information_summary": {
                                "type": "string"
                            },
                            "new_status": {
                                "type": "string",
                                "enum": ["empty", "in_progress", "complete"]
                            }
                        },
                        "required": ["key", "new_information_summary", "new_status"]
                    }
                }
            },
            "required": ["list"]
        }
        task4_prompt = f"""Based on the fields specifications, determine if the user answer contains relevant information for some fields other than the current field.
Update the information summary of the concerned fields with the user answer.
Compare the new information summary of the concerned fields with their answer criteria. For each field, if there is enough information, set the field status to "complete". If there is not enough information and the field was "empty", set the field status to "in_progress"
Return the list of the concerned fields, with their key, their new information summary and their new status.
Output STRICT JSON with this schema:
{output4_format}
"""
        step_messages += [
            {"role": "assistant", "content": text},
            {"role": "user", "content": task4_prompt}
        ]
        raw = await self._model_gateway.chat(
            messages=step_messages,
            model=self.VALIDATOR_MODEL,
            temperature=0.2,
        )
        text = (raw or "").strip()
        print(f"[DATA_COLLECTOR] DEBUG - Output task 4 : {text}")
        try:
            start = text.find("{")
            end = text.rfind("}") + 1
            data = json.loads(text[start:end])
            data_list = data.get("list")
            for item in data_list:
                if item.get("key") != current_field and state["stepData"]["field_status"].get(item.get("key")) != "complete":
                    state["stepData"]["field_status"][item.get("key")] = (item.get("new_status") or state["stepData"]["field_status"][item.get("key")])
                    state["stepData"]["field_information"][item.get("key")] = (item.get("new_information_summary") or state["stepData"]["field_information"][item.get("key")])
        except Exception:
            # Fail-safe: no update on other fields
            print("[DATA_COLLECTOR] DEBUG - Parsing of task 4 output has failed.")

        # Determine next step
        state["pending_prompt_id"] = None
        if state["stepData"]["field_status"][current_field] == "complete":
            next_field, step = self._next_unfilled_key(state["stepData"]["field_status"])
            if next_field == None:
                await adispatch_custom_event("tool_progress", {"step": self.TOTAL_STEPS, "total": self.TOTAL_STEPS}) # TODO : change args of dispatched event
                state["nextNode"] = "before_analyzer"
                self._log_model_quality_debug(state=state, current_field=current_field)
                return state
            state["stepData"]["current_field_key"] = next_field
            state["stepData"]["step"] = step
            await adispatch_custom_event("tool_progress", {"step": step, "total": self.TOTAL_STEPS}) # TODO : change args of dispatched event
        self._log_model_quality_debug(state=state, current_field=current_field)
        state["nextNode"] = "generate_question"
        return state
    
    async def before_analyzer_node(self, state: SubgraphState) -> SubgraphState:
        collected = state["stepData"].get("field_information", {})
        branch_a_topics = {
            "use_case_identification": collected.get("a_use_case_identification"),
            "technical_infrastructure_baseline": collected.get("a_technical_infrastructure_baseline"),
            "strategic_organizational_maturity": collected.get("a_strategic_organizational_maturity"),
            "roadmap_ecosystem": collected.get("a_roadmap_ecosystem"),
        }
        step_data = {
            "user_industry": collected.get("a_use_case_identification"),
            "branch_a_topics": branch_a_topics,
            "fields": collected,
        }
        await adispatch_custom_event(
            "tool_complete",
            {"tool_name": self.name, "step_data": step_data},
        )
        state["stepData"] = step_data
        state["nextNode"] = "analyzer"
        return state

    # --- Utils functions ---

    def _normalized_command(self, text: str) -> Optional[str]:
        v = (text or "").strip().lower()
        if v in {"/skip", "/clarify", "/cancel"}:
            return v
        return None
    
    def _next_unfilled_key(self, field_status: Dict[str, str]) -> Optional[str]:
        for i in range(len(self.FIELD_SPECS)):
            if field_status[self.FIELD_SPECS[i]["key"]] != "complete":
                return self.FIELD_SPECS[i]["key"], i+1
        return None, None

    def _write_information_status(self, stepData: QuantumDataCollectorState) -> str:
        complete_fields_str = "Complete or skipped fields (No more information needed) :"
        ongoing_fields_str = "In progress fields (partially filled fields) :"
        empty_fields_str = "Empty fields :"
        for field in self.FIELD_SPECS:
            field_status = stepData.get("field_status", {}).get(field["key"], "")
            field_information = stepData.get("field_information", {}).get(field["key"], "")
            if field_status == "empty":
                empty_fields_str += f"\n    - key : {field['key']}"
            elif field_status == "in_progress":
                ongoing_fields_str += f"\n    - key : {field['key']} ; information : {field_information}"
            elif field_status == "complete":
                complete_fields_str += f"\n    - key : {field['key']} ; information : {field_information}"
        return f"1. {complete_fields_str}\n\n2. {ongoing_fields_str}\n\n3. {empty_fields_str}"

    def _log_model_quality_debug(self, state: SubgraphState, current_field: str) -> None:
        question = self._latest_assistant_question(state["stepData"].get("messages", []))
        user_answer = state["stepData"].get("last_user_answer", "")
        stored_field_value = state["stepData"].get("field_information", {}).get(current_field, "")
        stored_field_status = state["stepData"].get("field_status", {}).get(current_field, "unknown")
        print(
            "\n[MODEL_QUALITY_DEBUG]"
            f"\n- model: {self.VALIDATOR_MODEL}"
            f"\n- current_field: {current_field}"
            f"\n- field_status: {stored_field_status}"
            f"\n- agent_question: {question}"
            f"\n- user_response: {user_answer}"
            f"\n- stored_field_information: {stored_field_value}"
            "\n[/MODEL_QUALITY_DEBUG]\n"
        )

    def _latest_assistant_question(self, messages: List[Dict[str, str]]) -> str:
        for message in reversed(messages):
            if message.get("role") == "assistant":
                return message.get("content", "")
        return "No assistant question found."