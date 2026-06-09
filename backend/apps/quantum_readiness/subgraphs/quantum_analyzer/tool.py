"""
Quantum Readiness Analyzer Tool - Layer 3.

Processes collected data to calculate scores.
Applies weighted scoring with confidence adjustments.
Maps results to archetype matrix.
Generates archetype narrative.
"""
import json
from typing import Any, Dict, TypedDict

from langchain_core.callbacks.manager import adispatch_custom_event
from langgraph.graph import END, START, StateGraph

from core.protocols import SubgraphProtocol
from core.state import SubgraphState
from core.model_gateway import ModelGateway

from tests.promptfoo_tests.shared_state import register


class QuantumAnalyzerState(TypedDict, total=False):
    """StepData for Quantum Readiness Analyzer Tool."""
    
    # Input data (from data collector)
    branch_a_topics: Dict

    # Output - Score
    quantum_opportunity_score: float # 0-100

    # Output - Archetype
    archetype: str
    archetype_narrative: str

class QuantumAnalyzerTool(SubgraphProtocol):
    """
    Analyzer Tool for Quantum Readiness assessment.
    
    Processes collected data to:
    - Calculate weighted scores with confidence penalties
    - Map to 2x2 archetype matrix
    - Generate archetype narrative
    """
    
    name = "quantum_analyzer"

    # TODO : complete criteria
    branch_a_specs = {
        "use_case_identification": {
            "industry": {
                "weight": 7,
                "question": "To what extent does the organisation's industry depends on quantum ?",
                "criteria": {
                    "min_score_cases": ["industry not specified", "no dependances with quantum"],
                    "max_score_cases": ["quantum-related industry"],
                },
            },
            "core_compute_problem": {
                "weight": 7,
                "question": "To what extent quantum can be used in this problem ?",
                "criteria": {},
            },
            "optimization": {
                "weight": 14,
                "question": "To what extent does the organisation run large-scale combinatorial optimization problems (logistics routing, scheduling, portfolio construction, resource allocation) ?",
                "criteria": {},
            },
            "intrinsic_quantum": {
                "weight": 14,
                "question": "To what extent does the organisation conduct molecular simulation, materials science, drug discovery research or any other research that has an intrinsic quantum nature ?",
                "criteria": {},
            },
        },
        "technical_infrastructure_baseline": {
            "classical_maturity": {
                "weight": 11,
                "question": "To what extent has the organisation currently implemented state-of-the-art classical solutions for the problems they are trying to solve ?",
                "criteria": {},
            },
            "internal_expertise": {
                "weight": 6,
                "question": "To what extent is the organisation self-sufficient regarding quantum internal expertise ?",
                "criteria": {},
            },
        },
        "strategic_organizational_maturity": {
            "adoption_posture": {
                "weight": 14,
                "question": "To what extent does the organization adopt a first-mover approach regarding quantum technologies ?",
                "criteria": {},
            },
            "ip_sensitivity": {
                "weight": 11,
                "question": "How sensitive is the IP of the organisation regarding their data, algorithms, partners, etc. ?",
                "criteria": {},
            },
        },
        "roadmap_ecosystem": {
            "internal_pilots": {
                "weight": 10,
                "question": "To what extent has the organisation conducted internal assessments or pilots related to quantum computing use cases ?",
                "criteria": {},
            },
            "ecosystem_partnerships": {
                "weight": 6,
                "question": "To what extent does the organisation takes part to any quantum ecosystem networks, consortia, or academic partnerships ?",
                "criteria": {},
            },
        },
    }
    
    def __init__(self, model_gateway: ModelGateway):
        self._model_gateway = model_gateway
    
    def describe(self) -> str:
        return "Analyzes collected quantum readiness data to calculate scores and determine archetype."
    
    def build(self):
        """Build the analyzer tool graph."""
        
        g = StateGraph(SubgraphState)
        g.add_node("analyze", self.analyze)
        g.add_node("init", self.init_step)
        g.add_edge(START, "init")
        g.add_edge("init", "analyze")
        g.add_edge("analyze", END)
        return g.compile()
    
    async def init_step(self, state: SubgraphState) -> SubgraphState:
        print(f"[ANALYZER] Input data keys: {list(state['stepData'].keys())}")

        stepData : QuantumAnalyzerState = {
            **(state["stepData"]),
            "branch_a_topics": state["stepData"]["branch_a_topics"],
            "quantum_opportunity_score": None,
            "archetype": None,
            "archetype_narrative": None,
        }
        state["currentStep"] = "analyzing"
        state["nextNode"] = "analyze"
        state["stepData"] = stepData
        state["error"] = None
        state["pending_prompt_id"] = None
        state["common_tool_output"] = None
        state["common_tool_input"] = None

        session_id = state.get("session_id", "unknown")
        print(f"[ANALYZER] Starting analysis for session: {session_id}")
        await adispatch_custom_event(
            "tool_start",
            {"tool_name": self.name, "total_steps": 1},
        )

        return state

    async def analyze(self, state: SubgraphState) -> SubgraphState:
        """
        Analyze collected data and calculate scores.
        
        Single-pass function - no user input needed.
        """
        
        branch_a_topics = state["stepData"].get("branch_a_topics", {}) or {}

        branch_a_result = await self._score_branch(branch_a_topics)
        branch_a_score = float(branch_a_result["total"])
        quantum_opportunity_score = branch_a_score
        state["stepData"]["quantum_opportunity_score"] = quantum_opportunity_score
        print(f"[ANALYZER] Branch A score: {branch_a_score:.1f}")

        if quantum_opportunity_score >= 70:
            archetype = "Act Now + Explore"
        elif quantum_opportunity_score >= 50:
            archetype = "Prepare + Explore"
        else:
            archetype = "Build Foundations"
        
        state["stepData"]["archetype"] = archetype
        print(f"[ANALYZER] Determined archetype: {archetype}")
        self._log_model_quality_debug_analyzer(
            branch_a_topics=branch_a_topics,
            branch_a_weights=self.branch_a_specs,
            branch_a_result=branch_a_result,
            branch_a_score=branch_a_score,
            archetype=archetype,
        )
        
        # Generate archetype narrative
        print(f"[ANALYZER] Generating archetype narrative...")
        narrative_prompt = self._prompt_narrative(
            archetype=archetype,
            company_name=state['stepData'].get('company_name_for_report') or state['stepData'].get('company_name', 'Unknown'),
            user_industry=state['stepData'].get('user_industry', 'Unknown'),
            branch_a_score=branch_a_score
        )
        narrative = await self._model_gateway.chat(
            messages=[{"role": "user", "content": narrative_prompt}],
            temperature=0.7,
        )
        
        state["stepData"]["archetype_narrative"] = narrative.strip()
        print(f"[ANALYZER] ✓ Analysis complete - archetype: {archetype}")
        
        # Store results in step_data for presenter tool
        opportunity_breakdown = {
            topic: {
                "weighted_points": float(data["score"]),
                "weight_points": int(data["max_score"]),
                "raw_score": float(data["score"]),
                "confidence": data["confidence"],
            }
            for topic, data in branch_a_result["topic_scores"].items()
        }

        unknowns = []
        for section_name, section in (
            ("branch_a", branch_a_result["topic_scores"]),
        ):
            for dim_name, dim_data in section.items():
                if dim_data.get("confidence", "low") == "low":
                    unknowns.append(
                        {
                            "section": section_name,
                            "dimension": dim_name,
                            "details": dim_data.get("details", "Low-confidence input"),
                        }
                    )

        step_data = {
            **(state["stepData"]),
            "branch_a_score": branch_a_score,
            "branch_a_band": self._branch_a_band(branch_a_score),
            "opportunity_breakdown": opportunity_breakdown,
            "unknowns": unknowns,
        }
        state["stepData"] = step_data
        state["nextNode"] = "presenter"
        
        # Mark tool as complete and expose canonical tool_result envelope.
        await adispatch_custom_event("tool_progress", {"step": 1, "total": 1})
        await adispatch_custom_event(
            "tool_complete",
            {"tool_name": self.name, "step_data": state["stepData"]},
        )
        print(f"[ANALYZER] ✓ Tool complete, output ready for presenter")
        
        return state
    
    # -------------------- Prompt functions -------------------------------

    @register(modelConfig={"temperature": 0.1})
    @classmethod
    def _prompt_score_branch(cls, topics: Dict[str, Dict]) -> str:
        output_format = {
            "type": "array",
            "items": {
                "oneOf": [
                    {
                        "type": "object",
                        "properties": {
                            "field": {
                                "type": "string",
                                "const": field,
                                "description": "ID of the field"
                            },
                            "rubrics": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "rubric": {
                                            "type": "string",
                                            "enum": content.keys(),
                                            "description": f"ID of the rubric inside the field {field}"
                                        },
                                        "score": {
                                            "type": "number",
                                            "description": "score for the rubric"
                                        },
                                        "reason": {
                                            "type": "string",
                                            "description": "A short sentence that explain why this score."
                                        }
                                    },
                                    "required": ["rubric", "score", "reason"],
                                    "additionalProperties": False
                                },
                                "description": "the scores for all rubric of the field"
                            }
                        },
                        "required": ["field", "rubrics"],
                        "additionalProperties": False
                    }
                    for field, content in cls.branch_a_specs.items()
                ]
            }
        }
        prompt = f"""You are a professional quantum assistant that helps managers to assess the quantum readiness of their company/structure.
You already collected the needed information from the manager. Each piece of information belongs to a specific rubric (e.g. 'industry' or 'classical_maturity'). Each rubric belongs to a main field (e.g. 'a_use_case_identification' or 'a_roadmap_ecosystem').
Here is the collected information :
{topics}

Your goal now is to assign a score for each rubric. To do this, I provide you a list of specifications for each rubric, with the following attributes :
- "weight": The max score for the rubric. Your score must always be between 0 and the weight.
- "question": The question the score should answer.
- "criteria": A list of possible indications to guide your scoring. It can be empty.
Here are the specifications :
{cls.branch_a_specs}

How you should assign a score to a rubric :
1) Analyse the collected information for the specific rubric
2) You can take the collected information from other rubrics into account as context.
3) Give a score from 0 to the weight of the rubric that answer the question of the rubric, based on the criteria of the rubric if they exist.
4) Explain how you chose the score.

Output STRICT JSON with this format :
{output_format}

Rules:
- Do not repeat keys.
- Do not include any text, notes, or markdown outside the JSON.
- Do not wrap the JSON in code fences.
"""
        return prompt
    
    @register(modelConfig={"temperature": 0.1})
    @classmethod
    def _prompt_narrative(cls, archetype: str, company_name: str, user_industry: str, branch_a_score: float):
        return f"""Generate a 2-3 sentence narrative explaining what the "{archetype}" archetype means for this company.

Context:
- Company: {company_name or 'unknown'}
- Industry: {user_industry or 'unknown'}
- Branch A (Quantum Competitiveness): {branch_a_score:.1f}/100

Be specific and actionable."""

    # -------------------- Other functions -------------------------------

    async def _score_branch(
        self,
        topics: Dict[str, Dict],
    ) -> Dict[str, Any]:
        prompt = self._prompt_score_branch(topics)
        parsed_scores: Dict[str, Dict[str, Any]] = {}
        raw_model_output = ""
        try:
            raw = await self._model_gateway.chat(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
            )
            raw_model_output = (raw or "").strip()
            raw_model_output = raw_model_output.replace("```json", "").replace("```", "").strip()
            start = raw_model_output.find("[")
            end = raw_model_output.rfind("]") + 1
            data = json.loads(raw_model_output[start:end]) if start >= 0 and end > start else []
            for item in data:
                if isinstance(item, dict) and item.get("field") and item["field"] in self.branch_a_specs.keys() and item.get("rubrics"):
                    parsed_scores[str(item["field"])] = {}
                    for item2 in item.get("rubrics"):
                        if (
                            isinstance(item2, dict)
                            and item2.get("rubric")
                            and item2["rubric"] in self.branch_a_specs[item["field"]].keys()
                            and item2.get("score") is not None
                        ):
                            parsed_scores[str(item["field"])][str(item2["rubric"])] = {
                                "score": int(item2.get("score", 0)),
                                "reason": str(item2.get("reason", "")),
                            }
                        else:
                            print("[ANALYZER] ⚠ INFO - invalid rubric item in scoring AI output")
                else:
                    print("[ANALYZER] ⚠ INFO - invalid field item in scoring AI output")
        except Exception:
            parsed_scores = {}
            raw_model_output = raw_model_output or "ERROR: failed to parse model scoring output."
        
        field_scores = {}
        total = 0.0
        field_trace = {}
        for field, rubrics in self.branch_a_specs.items():
            score_field = 0
            weight_field = 0
            missing_rubrics = 0
            missing_field = field not in parsed_scores
            field_trace[field] = {}
            for rubric, spec in rubrics.items():
                weight = spec["weight"]
                weight_field += weight
                answer = topics.get(field, {}).get(rubric, "")
                has_answer = bool(str(answer).strip()) if answer is not None else False
                fallback = int(round(weight * 0.5)) if has_answer else 0
                score = parsed_scores.get(field, {}).get(rubric, {}).get("score", fallback)
                score = max(0, min(int(weight), int(score)))
                used_fallback = field not in parsed_scores or rubric not in parsed_scores[field]
                if used_fallback:
                    missing_rubrics += 1
                score_field += score
                total += score
                field_trace[field][rubric] = {
                    "input_answer": answer or "",
                    "parsed_score": parsed_scores.get(field, {}).get(rubric, {}).get("score"),
                    "reason": parsed_scores.get(field, {}).get(rubric, {}).get("reason", ""),
                    "fallback_score": fallback,
                    "final_score": score,
                    "used_fallback": used_fallback,
                    "confidence": "medium" if has_answer else "low",
                }
            confidence = ""
            if missing_field:
                confidence = "0%"
            else:
                confidence = str(int(75 - (missing_rubrics/len(self.branch_a_specs[field].keys())*75))) + "%"
            field_scores[field] = {
                "score": score_field,
                "max_score": weight_field,
                "confidence": confidence,
            }
        return {
            "total": total,
            "topic_scores": field_scores,
            "debug": {
                "specs": self.branch_a_specs,
                "raw_model_output": raw_model_output,
                "parsed_scores": parsed_scores,
                "scoring_trace": field_trace,
            }
        }
    
    def _branch_a_band(self, score: float) -> Dict[str, str]:
        if score <= 25:
            return {"name": "Quantum Unaware", "recommended_focus": "Build awareness and map high-value use cases before investing."}
        if score <= 45:
            return {"name": "Quantum Curious", "recommended_focus": "Validate use cases against strong classical baselines."}
        if score <= 65:
            return {"name": "Quantum Exploring", "recommended_focus": "Run internal pilots and secure a dedicated budget line."}
        if score <= 80:
            return {"name": "Quantum Preparing", "recommended_focus": "Deepen capability, formalize roadmap, monitor competitors."}
        return {"name": "Quantum Ready", "recommended_focus": "Scale validated pilots and protect quantum-derived IP."}

    def _log_model_quality_debug_analyzer(
        self,
        branch_a_topics: Dict[str, Any],
        branch_a_weights: Dict[str, Any],
        branch_a_result: Dict[str, Any],
        branch_a_score: float,
        archetype: str,
    ) -> None:
        debug_payload = branch_a_result.get("debug", {})
        print(
            "\n[MODEL_QUALITY_DEBUG_ANALYZER]"
            f"\n- model: {self._model_gateway.default_model}"
            f"\n- scoring_branch: {debug_payload.get('branch_name', 'Branch A')}"
            f"\n- input_topics: {json.dumps(branch_a_topics, ensure_ascii=False)}"
            f"\n- weights: {json.dumps(branch_a_weights, ensure_ascii=False)}"
            f"\n- raw_model_output: {debug_payload.get('raw_model_output', '')}"
            f"\n- parsed_scores: {json.dumps(debug_payload.get('parsed_scores', {}), ensure_ascii=False)}"
            f"\n- scoring_trace: {json.dumps(debug_payload.get('scoring_trace', {}), ensure_ascii=False)}"
            f"\n- final_branch_a_score: {branch_a_score:.1f}"
            f"\n- final_archetype: {archetype}"
            "\n[/MODEL_QUALITY_DEBUG_ANALYZER]\n"
        )
