"""Writer Agent: compiles the Researcher's findings into a professional
competitor analysis report (Pydantic-validated), screens it for sensitive
data, and saves it to disk pending human approval.
"""
from __future__ import annotations

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from app.config import get_settings
from app.graph.state import GraphState
from app.instrumentation import get_tracer
from app.logging_utils import log_event
from app.schemas import ReportDraft, ReportDraftContent
from app.tools.report_writer import finalize_draft, save_report

_SYSTEM_PROMPT = """You are the Writer Agent. Compile the supplied research findings
into a professional, executive-ready competitor analysis report. Be specific and cite
concrete numbers/facts from the findings where available. Do not invent data that isn't
in the findings. Structure the report with clear sections (e.g. Market Overview,
Competitor Landscape, Pricing & Products, Financial Performance, Risks & Opportunities,
Recommendations)."""


def _findings_to_text(findings) -> str:
    lines = []
    for f in findings:
        lines.append(f"[{f.kind}] {f.summary}")
    return "\n".join(lines)


def writer_node(state: GraphState) -> dict:
    settings = get_settings()
    session_id = state["session_id"]
    findings = state.get("findings", [])

    llm = ChatOpenAI(model=settings.openai_model, temperature=0.2, api_key=settings.openai_api_key or "not-set")
    structured_llm = llm.with_structured_output(ReportDraftContent)

    prompt = f"Task: {state['task']}\n\nFindings:\n{_findings_to_text(findings)}"
    with get_tracer().span("writer.compile_report", agent="writer") as span:
        content: ReportDraftContent = structured_llm.invoke(
            [
                SystemMessage(content=_SYSTEM_PROMPT),
                HumanMessage(content=prompt),
            ]
        )
        span.record_llm_usage(settings.openai_model, prompt_text=prompt, completion_text=content.model_dump_json())
        span.set_metadata(session_id=session_id, n_findings=len(findings))
    sources = sorted(
        {
            getattr(f.detail, "url", None) or getattr(f.detail, "source", None) or f.kind
            for f in findings
            if f.detail is not None
        }
    )
    draft = ReportDraft(
        title=content.title,
        executive_summary=content.executive_summary,
        sections=content.sections,
        sources=sources,
    )
    draft = finalize_draft(draft)
    report_path = save_report(draft, session_id)

    log_event(
        session_id=session_id,
        agent="writer",
        action="compile_report",
        input_summary=f"{len(findings)} findings",
        output_summary=draft.title,
        contains_sensitive_data=draft.contains_sensitive_data,
        report_path=str(report_path),
    )

    return {"draft": draft, "report_path": str(report_path)}
