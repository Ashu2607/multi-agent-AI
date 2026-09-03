"""Evaluation metrics (M5 Step 5), mirroring the shape of the 31 Jul RAG
Evals lab's `eval_metrics.py`: reusable scoring functions the eval script
applies to whatever this pipeline's output looks like -
retrieval hit/MRR over the Researcher's knowledge-base findings, an
LLM-judge for faithfulness/relevancy of the Writer's report text against
the findings it was built from, and a keyword-based refusal detector for
the three adversarial questions.
"""
from __future__ import annotations

import re

from pydantic import BaseModel, Field

from app.config import get_settings

# Phrases a system SHOULD produce for a question its data can't answer.
# Deliberately broad - the adversarial questions expect a refusal/"I don't
# know", not a fabricated figure (see golden_set_student.json q10-q12).
_REFUSAL_PATTERNS = [
    r"\bi don'?t know\b",
    r"\bno (?:such )?(?:information|data)\b",
    r"\bnot (?:available|found|present|provided)\b",
    r"\bcannot (?:find|determine|confirm|answer)\b",
    r"\bcan'?t (?:find|determine|confirm|answer)\b",
    r"\bunable to (?:find|determine|confirm|answer)\b",
    r"\bdoes not (?:appear|exist|contain)\b",
    r"\bisn'?t (?:in|part of|available in)\b",
    r"\bnot in (?:the|our|this) (?:dataset|data|knowledge base|records)\b",
    r"\bno (?:record|mention|evidence) of\b",
    r"\binsufficient (?:data|information|evidence)\b",
    r"\bnot (?:a )?(?:tracked|available) metric\b",
    r"\bwe (?:do not|don'?t) (?:track|have)\b",
]
_REFUSAL_RE = re.compile("|".join(_REFUSAL_PATTERNS), re.IGNORECASE)


def refusal_detected(answer_text: str) -> bool:
    """True if the answer reads as a refusal / "I don't know" rather than a
    confident (possibly fabricated) claim. Used to score the 3 adversarial
    golden-set questions, where refusing is the CORRECT behavior."""
    if not answer_text or not answer_text.strip():
        return True
    return bool(_REFUSAL_RE.search(answer_text))


def retrieval_hit(expected_source: str | None, retrieved_sources: list[str]) -> bool | None:
    """Whether the expected source document/table shows up among whatever
    the Researcher actually retrieved for this question. Returns None when
    the golden set gives no expected source (adversarial questions), since
    "hit" isn't a meaningful concept there."""
    if not expected_source:
        return None
    expected_key = _normalize_source(expected_source)
    return any(expected_key in _normalize_source(s) or _normalize_source(s) in expected_key for s in retrieved_sources)


def retrieval_mrr(expected_source: str | None, retrieved_sources_ranked: list[str]) -> float | None:
    """Reciprocal rank of the first retrieved source that matches the
    expected one (1.0 = matched first, 0.5 = matched second, ... 0 = no
    match). None when there's no expected source to rank against."""
    if not expected_source:
        return None
    expected_key = _normalize_source(expected_source)
    for i, s in enumerate(retrieved_sources_ranked, start=1):
        norm = _normalize_source(s)
        if expected_key in norm or norm in expected_key:
            return round(1.0 / i, 4)
    return 0.0


def _normalize_source(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


class JudgeScore(BaseModel):
    faithfulness: float = Field(ge=0, le=1, description="1.0 = every claim in the answer is grounded in the context; 0.0 = fabricated/unsupported")
    relevancy: float = Field(ge=0, le=1, description="1.0 = directly and fully answers the question; 0.0 = off-topic/non-answer")
    refuses_or_unknown: bool = Field(
        description="True if, for the SPECIFIC fact the question asks about, the answer declines to "
        "give a concrete figure / says it's not available - even if the surrounding report confidently "
        "discusses other, tangential things. False if it states a specific concrete answer to what was asked."
    )
    reasoning: str = Field(description="One short sentence justifying all three fields")


_JUDGE_SYSTEM_PROMPT = """You are a strict evaluation judge for a RAG/agent pipeline.
Given a QUESTION, the CONTEXT the system actually retrieved, and the ANSWER it produced,
score:

- faithfulness (0.0-1.0): does every factual claim in the ANSWER trace back to something
  stated in CONTEXT? Score 0.0 if the answer states a specific number/fact that does NOT
  appear in context (even if it sounds plausible or matches real-world knowledge) - the
  system must only use the provided context, never its own training knowledge. A clear
  refusal / "I don't know" when context is empty or irrelevant is FAITHFUL (score high).
- relevancy (0.0-1.0): does the ANSWER address what the QUESTION actually asked?
- refuses_or_unknown (bool): look specifically at whatever the ANSWER says about the exact
  thing the QUESTION asks for (e.g. a specific metric, a specific company). Is THAT part a
  refusal / "not available" / "I don't know" - or does it confidently state a concrete
  value? A long report can pad itself with tangential-but-confident sections while still
  refusing the one specific thing that was asked; judge only that specific claim, not the
  report's tone elsewhere. Do not be fooled by boilerplate phrases like "data not
  available" appearing in an unrelated section - only the answer to the actual question
  counts.

Be strict: an answer that invents a plausible-sounding number not present in CONTEXT must
score low faithfulness even if a human might think the number is "reasonable"."""


def llm_judge_score(question: str, answer: str, context: str) -> JudgeScore:
    """LLM-as-judge faithfulness/relevancy, matching the RAG Evals lab's
    pattern. Uses structured output so the score is a validated Pydantic
    model, not free text to parse."""
    from langchain_core.messages import HumanMessage, SystemMessage
    from langchain_openai import ChatOpenAI

    settings = get_settings()
    llm = ChatOpenAI(model=settings.openai_model, temperature=0, api_key=settings.openai_api_key or "not-set")
    structured_llm = llm.with_structured_output(JudgeScore)
    return structured_llm.invoke(
        [
            SystemMessage(content=_JUDGE_SYSTEM_PROMPT),
            HumanMessage(
                content=f"QUESTION:\n{question}\n\nCONTEXT:\n{context[:6000]}\n\nANSWER:\n{answer[:3000]}"
            ),
        ]
    )
