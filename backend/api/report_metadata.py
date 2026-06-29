"""Helpers for report download metadata sent to the frontend."""
from typing import Any, Dict, List, Optional

COLLECTED_FIELD_LABELS: Dict[str, str] = {
    "a_use_case_identification": "Use Case Identification",
    "a_technical_infrastructure_baseline": "Technical & Infrastructure Baseline",
    "a_strategic_organizational_maturity": "Strategic & Organizational Maturity",
    "a_roadmap_ecosystem": "Roadmap & Ecosystem",
}

FIELD_ORDER = list(COLLECTED_FIELD_LABELS.keys())


def _step_data_has_collected_fields(step_data: Dict[str, Any]) -> bool:
    fields = step_data.get("fields") or step_data.get("field_information") or {}
    return any(str(fields.get(key, "") or "").strip() for key in FIELD_ORDER)


def extract_step_data_from_state(state_snapshot: Any) -> Dict[str, Any]:
    """Extract stepData from core graph state or nested subgraph checkpoints."""
    if not state_snapshot or not hasattr(state_snapshot, "values"):
        return {}

    values = state_snapshot.values or {}
    step_data = values.get("stepData") or {}
    if _step_data_has_collected_fields(step_data) or step_data.get("company_name"):
        return step_data

    tasks = getattr(state_snapshot, "tasks", None) or []
    for task in tasks:
        nested = getattr(task, "state", None)
        if not nested:
            continue
        nested_data = extract_step_data_from_state(nested)
        if _step_data_has_collected_fields(nested_data) or nested_data.get("company_name"):
            return nested_data

    return step_data


def resolve_report_company_name(step_data: Dict[str, Any]) -> str:
    """Return the best display name for the report header and PDF filename."""
    company = (
        step_data.get("company_name")
        or step_data.get("company_name_for_report")
        or ""
    )
    company = str(company).strip()
    if not company or company.lower() == "unknown":
        return "Your Company"
    return company


def build_collected_data_sections(step_data: Dict[str, Any]) -> List[Dict[str, str]]:
    """Build human-readable sections from collected assessment fields."""
    fields = step_data.get("fields") or step_data.get("field_information") or {}
    sections: List[Dict[str, str]] = []
    for key in FIELD_ORDER:
        content = str(fields.get(key, "") or "").strip()
        if not content:
            continue
        sections.append(
            {
                "title": COLLECTED_FIELD_LABELS.get(key, key),
                "content": content,
            }
        )
    return sections


def format_collected_data_appendix_markdown(step_data: Dict[str, Any]) -> str:
    """Markdown appendix with all gathered assessment answers."""
    sections = build_collected_data_sections(step_data)
    if not sections:
        return ""

    lines = [
        "",
        "## 5. COLLECTED ASSESSMENT DATA",
        "",
        "_Context gathered during this assessment. Use this section when continuing with the Roadmap Chatbot._",
        "",
    ]
    for section in sections:
        lines.append(f"### {section['title']}")
        lines.append(section["content"])
        lines.append("")
    lines.append("---")
    return "\n".join(lines)


def build_report_download_metadata(step_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Build metadata for PDF export when a quantum readiness report exists."""
    if not step_data:
        return None
    return {
        "company_name": resolve_report_company_name(step_data),
        "collected_data": build_collected_data_sections(step_data),
    }
