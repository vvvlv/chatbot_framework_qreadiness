"""
Quantum Readiness Presenter/RAG Tool - Layer 3.

Retrieves benchmark documents via RAG.
Generates prioritized action list.
Formats final readiness report.
"""
import json
import traceback
from datetime import date
from typing import Dict, List, TypedDict

from langchain_core.callbacks.manager import adispatch_custom_event
from langgraph.graph import END, START, StateGraph

from api.report_metadata import build_report_download_metadata, format_collected_data_appendix_markdown
from core.protocols import SubgraphProtocol, ToolProtocol
from core.state import SubgraphState
from core.model_gateway import ModelGateway

from tests.promptfoo_tests.shared_state import register


class QuantumPresenterState(TypedDict, total=False):
    """State for Quantum Readiness Presenter Tool."""
    
    # Input data (from analyzer)
    user_industry: str
    quantum_opportunity_score: float
    archetype: str
    archetype_narrative: str
    branch_a_topics: Dict
    branch_a_score: float
    branch_a_band: Dict[str, str]
    opportunity_breakdown: dict
    unknowns: list

    # Output
    benchmark_documents: List[Dict]
    priority_actions: List[Dict]
    timeline_guidance: str
    company_name: str
    industry: str
    readiness_report: str
    next_step: str


class QuantumPresenterTool(SubgraphProtocol):
    """
    Presenter/RAG Tool for Quantum Readiness assessment.
    
    Formats results and retrieves benchmark documents.
    Generates prioritized action list and final report.
    """
    
    name = "quantum_presenter"
    
    def __init__(self, model_gateway: ModelGateway, retriever: ToolProtocol):
        self._model_gateway = model_gateway
        self._retriever = retriever
    
    def describe(self) -> str:
        return "Formats quantum readiness results and generates prioritized action list with benchmark references."
    
    def build(self):
        """Build the presenter tool graph."""
        
        g = StateGraph(SubgraphState)
        g.add_node("init", self.init_node)
        g.add_node("rag", self._retriever.build())
        g.add_node("present", self.present_node)
        g.add_edge(START, "init")
        g.add_edge("init", "rag")
        g.add_edge("rag", "present")
        g.add_edge("present", END)
        return g.compile()
    
    async def init_node(self, state: SubgraphState) -> SubgraphState:
        session_id = state.get("session_id", "unknown")
        print(f"[PRESENTER] Generating report for session: {session_id}")

        print(f"[PRESENTER] Input data keys: {list(state['stepData'].keys())}")

        await adispatch_custom_event(
            "tool_start",
            {"tool_name": self.name, "total_steps": 1},
        )

        stepData : QuantumPresenterState = {
            **(state["stepData"]),
            "benchmark_documents": None,
            "priority_actions": None,
            "timeline_guidance": None,
            "readiness_report": None,
            "next_step": None
        }

        state["currentStep"] = "presenting"
        state["nextNode"] = "present"
        state["stepData"] = stepData
        state["error"] = None
        state["pending_prompt_id"] = None
        state["common_tool_output"] = None

        # Find company name and user industry from field "a_use_case_identification"
        print(f"[PRESENTER] Retrieving user industry information...")
        provided_company_name = (state["stepData"].get("company_name_for_report") or "").strip()
        extracted_company_candidate = "unknown"
        industry_prompt = self._prompt_extract_company_name(user_message=state['stepData'].get('user_industry', 'no user message'))
        try:
            industry_response = await self._model_gateway.chat(
                messages=[{"role": "user", "content": industry_prompt}],
                temperature=0.3,
            )
            
            # Try to parse JSON
            if "{" in industry_response and "}" in industry_response:
                json_start = industry_response.find("{")
                json_end = industry_response.rfind("}") + 1
                json_str = industry_response[json_start:json_end]
                industry_result = json.loads(json_str)
                state["stepData"]["industry"] = industry_result.get("industry", "unknown")
                extracted_company_candidate = str(industry_result.get("company_name", "unknown") or "unknown")
                print(f"[PRESENTER] ✓ Retrieved user's company name and industry")
            else:
                print(f"[PRESENTER] ⚠ Could not parse actions JSON from LLM response")
                state["stepData"]["industry"] = "unknown"
        except Exception as e:
            print(f"[PRESENTER] ✗ Error finding user industry information: {e}")
            traceback.print_exc()
            state["stepData"]["industry"] = "unknown"

        if provided_company_name and provided_company_name.lower() != "unknown":
            resolved_company_name = provided_company_name[:120]
        else:
            resolved_company_name = await self._resolve_company_name(
                provided_company_name=provided_company_name,
                extracted_candidate=extracted_company_candidate,
                user_context=str(state["stepData"].get("user_industry", "") or ""),
            )
        state["stepData"]["company_name"] = resolved_company_name or "unknown"

        # Retrieve benchmark documents via RAG
        print(f"[PRESENTER] Retrieving benchmark documents...")
        benchmark_query = f"""Quantum computing timelines, roadmaps, and qubit estimates for {state["stepData"].get('industry', 'unknown')} industry.
Include practical deployment roadmaps and industry adoption benchmarks."""
        args_rag = {
            "action": "retrieve",
            "query": benchmark_query,
            "top_k": 5
        }
        state["common_tool_input"] = {
            "nextNode": "present",
            "args": args_rag
        }

        return state

    async def present_node(self, state: SubgraphState) -> SubgraphState:
        """
        Format results and generate final report.
        
        Single-pass function - no user input needed.
        """
        
        opp_score = state["stepData"].get("quantum_opportunity_score", 0)
        archetype = state["stepData"].get("archetype", "Unknown")
        print(f"[PRESENTER] Scores - Opportunity: {opp_score:.1f}, Archetype: {archetype}")

        # process rag tool answer
        if state["common_tool_output"].get("error", False):
            print(f"[PRESENTER] ⚠ Error retrieving benchmarks: {state['error']}")
            state["benchmark_documents"] = []
        else:
            state["stepData"]["benchmark_documents"] = state["common_tool_output"]["answer"]
            state["common_tool_output"] = None
            print(f"[PRESENTER] Retrieved {len(state['stepData']['benchmark_documents'])} benchmark documents")
        
        # Format benchmark context
        benchmark_context = "\n---\n".join(
            doc.get("content", str(doc)) for doc in state["stepData"]["benchmark_documents"]
        ) if state["stepData"]["benchmark_documents"] else "No benchmark documents available."
        
        # Generate prioritized actions
        print(f"[PRESENTER] Generating prioritized actions...")
        actions_prompt = self._prompt_actions(
            industry=state['stepData'].get('industry', 'Unknown'),
            archetype=state['stepData'].get('archetype', 'Unknown'),
            opportunity_score=state['stepData'].get('quantum_opportunity_score', 0),
            benchmark_context=benchmark_context,
        )
        try:
            actions_response = await self._model_gateway.chat(
                messages=[{"role": "user", "content": actions_prompt}],
                temperature=0.3,
            )
            
            # Try to parse JSON
            if "{" in actions_response and "}" in actions_response:
                json_start = actions_response.find("{")
                json_end = actions_response.rfind("}") + 1
                json_str = actions_response[json_start:json_end]
                actions_result = json.loads(json_str)
                state["stepData"]["priority_actions"] = actions_result.get("priority_actions", [])
                state["stepData"]["next_step"] = actions_result.get("next_step", "")
                print(f"[PRESENTER] ✓ Generated {len(state['stepData']['priority_actions'])} priority actions")
            else:
                print(f"[PRESENTER] ⚠ Could not parse actions JSON from LLM response")
                state["stepData"]["priority_actions"] = []
                state["stepData"]["next_step"] = ""
        except Exception as e:
            print(f"[PRESENTER] ✗ Error generating actions: {e}")
            traceback.print_exc()
            state["stepData"]["priority_actions"] = []
            state["stepData"]["next_step"] = ""
        
        # Generate timeline guidance # TODO : UNUSED FOR NOW
#         print(f"[PRESENTER] Generating timeline guidance...")
#         timeline_prompt = f"""Based on the benchmark documents and company context, provide timeline guidance.

# Benchmark context:
# {benchmark_context[:1000]}

# Company: 
#     - name : {state['stepData'].get('company_name', 'Unknown')}
#     - industry : {state['stepData'].get('industry', 'Unknown')}
# Current opportunity score: {state['stepData'].get('quantum_opportunity_score', 0):.1f}

# Provide specific timeline recommendations based on the benchmarks."""
        
        # try:
        #     timeline_response = await self._model_gateway.chat(
        #         messages=[{"role": "user", "content": timeline_prompt}],
        #         temperature=0.3,
        #     )
        #     state["stepData"]["timeline_guidance"] = timeline_response.strip()
        #     print(f"[PRESENTER] ✓ Timeline guidance generated")
        # except Exception as e:
        #     print(f"[PRESENTER] ⚠ Error generating timeline: {e}")
        #     state["stepData"]["timeline_guidance"] = "Timeline guidance unavailable."

        # Generate final report
        print(f"[PRESENTER] Formatting final report...")
        state["stepData"]["readiness_report"] = self._format_report(state["stepData"])
        
        # Set output for core graph
        state["output"] = state["stepData"]["readiness_report"]
        print(f"[PRESENTER] ✓ Report generated ({len(state['stepData']['readiness_report'])} chars)")

        report_metadata = build_report_download_metadata(state["stepData"])
        if report_metadata:
            collected_count = len(report_metadata.get("collected_data") or [])
            print(f"[PRESENTER] Report download metadata: {collected_count} collected sections")
            await adispatch_custom_event("report_download_metadata", report_metadata)
        
        await adispatch_custom_event("tool_progress", {"step": 1, "total": 1})
        await adispatch_custom_event(
            "tool_complete",
            {"tool_name": self.name, "report_len": len(state["stepData"]["readiness_report"])},
        )
        return state

# --------------------- Prompt functions --------------------------------

    @register(modelConfig={"temperature": 0.3})
    @classmethod
    def _prompt_extract_company_name(cls, user_message: str) -> str:
        return f"""Based on the following user message, identify the company name and the industry of the user. Return "unknown" if the user doesn't contain the information needed.

User message :
{user_message}

Return JSON:
{{
"company_name": "<user company name>" or "unknown",
"industry": "<user industry>" or "unknown"
}}
"""
    
    @register(modelConfig={"temperature": 0.0})
    @classmethod
    def _prompt_resolve_company_name(
        cls,
        provided_company_name: str,
        extracted_candidate: str,
        user_context: str,
    ) -> str:
        return f"""Resolve the best company name for a report header.

Provided name from user preference step: {provided_company_name or "unknown"}
Candidate extracted from context: {extracted_candidate or "unknown"}
User context: {user_context}

Return STRICT JSON:
{{
  "company_name": "<name or unknown>",
  "is_valid_company_name": true/false
}}

Rules:
- Prefer the provided name if it is a real company name.
- If provided is invalid or missing, use extracted candidate if valid.
- If neither is valid, return unknown/false.
- Reject sentence fragments, refusals, or descriptive statements.
- No markdown.
"""
    
    @register(modelConfig={"temperature": 0.3})
    @classmethod
    def _prompt_actions(
        cls,
        industry: str,
        archetype: str,
        opportunity_score: float,
        benchmark_context: str,
    ) -> str:
        return f"""Generate a prioritized action list for quantum readiness.

Company context:
- Industry: {industry}
- Archetype: {archetype}

Scores:
- Quantum Opportunity: {opportunity_score:.1f}/100

Benchmark documents:
{benchmark_context[:1000]}  # Truncate for context

Generate:
1. Top 3 priority actions (most urgent first)
2. For each action, provide:
- Specific, concrete action item
- Reference (industry report, roadmap, benchmark publication, etc.)
- Urgency level

Return JSON:
{{
"priority_actions": [
    {{
        "action": "...",
        "priority": 1,
        "reference": "Industry benchmark report",
        "urgency": "high"
    }},
    ...
],
"next_step": "One concrete action for next 30 days"
}}"""

# --------------------- Other functions ---------------------------------

    def _format_report(self, step_data: Dict) -> str:
        """Format the final quantum readiness report."""
        company = step_data.get("company_name") or "Your Company"
        if company == "unknown":
            company = "Your Company"
        industry = step_data.get("industry") or "Unknown Sector"
        if industry == "unknown":
            industry = "Unknown Sector"
        today = date.today().isoformat()
        opp = step_data.get("quantum_opportunity_score", 0.0)
        branch_a_score = step_data.get("branch_a_score", opp)
        branch_a_band = (step_data.get("branch_a_band") or {}).get("name", "Unknown")
        branch_a_focus = (step_data.get("branch_a_band") or {}).get("recommended_focus", "")
        archetype = step_data.get("archetype", "Unknown")
        narrative = step_data.get("archetype_narrative", "")
        opp_breakdown = step_data.get("opportunity_breakdown", {})
        unknowns = step_data.get("unknowns", []) # TODO : not in the report for now
        # unknowns_text = ""
        # for item in unknowns:
        #     unknowns_text += f"  ⚠️ You were unsure about {item["section"]} - {item["dimension"]}\n"
        
        report = f"""
--- 
# QUANTUM READINESS REPORT  
Company: {company} | Sector: {industry} | Date: {today}  

---

## 1. SCORES AT A GLANCE  
    - Branch A (Quantum Competitiveness):     {branch_a_score:.0f} / 100  📈 {branch_a_band}

## 2. YOUR ARCHETYPE  
   → "{archetype}"  
   {narrative}

## 3. SCORE BREAKDOWN  
    1. Branch A (Quantum Competitiveness)
        - Use Case Identification        {opp_breakdown.get('use_case_identification', {}).get('weighted_points', 0):>4.0f} / 35   {self._confidence_marker(opp_breakdown.get('use_case_identification', {}).get('confidence', 'low'))}
        - Tech/Infrastructure Baseline   {opp_breakdown.get('technical_infrastructure_baseline', {}).get('weighted_points', 0):>4.0f} / 25   {self._confidence_marker(opp_breakdown.get('technical_infrastructure_baseline', {}).get('confidence', 'low'))}
        - Strategic/Org Maturity         {opp_breakdown.get('strategic_organizational_maturity', {}).get('weighted_points', 0):>4.0f} / 25   {self._confidence_marker(opp_breakdown.get('strategic_organizational_maturity', {}).get('confidence', 'low'))}
        - Roadmap & Ecosystem            {opp_breakdown.get('roadmap_ecosystem', {}).get('weighted_points', 0):>4.0f} / 15   {self._confidence_marker(opp_breakdown.get('roadmap_ecosystem', {}).get('confidence', 'low'))}

## 4. WHERE TO FOCUS NEXT  
   You are currently positioned as "{branch_a_band}" on quantum competitiveness.  
   Your most important focus areas are:  
   - Quantum Competitiveness: {branch_a_focus or 'Define focused pilots and decision milestones.'}  
   If you want a practical action plan, the Roadmap Chatbot can translate these priorities into concrete next steps and timeline options.
"""
        
        report += format_collected_data_appendix_markdown(step_data)
        if not report.rstrip().endswith("---"):
            report += "  \n---\n"
        
        return report

    def _confidence_marker(self, level: str) -> str:
        if level == "low":
            return "⚠️"
        if level == "medium":
            return "•"
        return ""
    
    def _get_opportunity_level(self, score: float) -> str:
        """Get opportunity level description."""
        if score >= 70:
            return "High Opportunity"
        elif score >= 50:
            return "Moderate Opportunity"
        else:
            return "Low Opportunity"

    async def _resolve_company_name(
        self,
        provided_company_name: str,
        extracted_candidate: str,
        user_context: str,
    ) -> str:
        prompt = self._prompt_resolve_company_name(provided_company_name, extracted_candidate, user_context)
        try:
            response = await self._model_gateway.chat(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0,
            )
            text = (response or "").strip()
            start = text.find("{")
            end = text.rfind("}") + 1
            data = json.loads(text[start:end]) if start >= 0 and end > start else {}
            company_name = " ".join(str(data.get("company_name", "")).strip().split()).strip("\"'")
            if not bool(data.get("is_valid_company_name")):
                return "unknown"
            if not company_name or company_name.lower() == "unknown":
                return "unknown"
            return company_name[:120]
        except Exception:
            return "unknown"
