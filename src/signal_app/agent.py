from __future__ import annotations

import re
import time
import uuid
from datetime import date, timedelta
from typing import Literal, Protocol, TypedDict

import structlog
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from signal_app.analytics import GrowthResult, calculate_growth

logger = structlog.get_logger(__name__)


class QuestionPlan(BaseModel):
    action: Literal["calculate_growth", "unsupported"]
    days: int = Field(default=30, ge=1, le=3650)
    metric: Literal["listener_count", "listen_count"] = "listener_count"


class QuestionInterpreter(Protocol):
    def interpret(self, question: str) -> QuestionPlan: ...


class RuleBasedQuestionInterpreter:
    """Offline fallback used for local development and deterministic tests."""

    def interpret(self, question: str) -> QuestionPlan:
        lowered = question.lower()
        if not any(word in lowered for word in ("grow", "growth", "change", "increased")):
            return QuestionPlan(action="unsupported")
        match = re.search(r"(?:last|over)\s+(\d+)\s+days?", lowered)
        days = int(match.group(1)) if match else 30
        metric = "listen_count" if "plays" in lowered or "listens" in lowered else "listener_count"
        return QuestionPlan(action="calculate_growth", days=min(days, 3650), metric=metric)


class OpenAIQuestionInterpreter:
    """LLM-backed intent planner with a strict structured output contract."""

    def __init__(self, *, model: str, api_key: str) -> None:
        from langchain_openai import ChatOpenAI

        self._model = ChatOpenAI(
            model=model, api_key=api_key, temperature=0
        ).with_structured_output(QuestionPlan)

    def interpret(self, question: str) -> QuestionPlan:
        result = self._model.invoke(
            "Plan a Signal music analytics question. Only calculate_growth is currently supported. "
            "Extract the requested lookback in days and metric; do not calculate anything.\n\n"
            f"Question: {question}"
        )
        if not isinstance(result, QuestionPlan):
            return QuestionPlan.model_validate(result)
        return result


class ToolExecution(BaseModel):
    tool: str
    arguments: dict[str, str | int]
    duration_ms: float
    success: bool


class QueryResponse(BaseModel):
    run_id: uuid.UUID
    answer: str
    supporting_data: GrowthResult | None
    tools: list[ToolExecution]
    sources: list[str]
    caveats: list[str]


class AgentState(TypedDict, total=False):
    question: str
    artist_id: uuid.UUID
    artist_name: str
    end_date: date
    source: str
    plan: QuestionPlan
    growth: GrowthResult
    tools: list[ToolExecution]
    answer: str
    caveats: list[str]


def _format_answer(artist_name: str, growth: GrowthResult) -> str:
    if growth.percentage_change is not None:
        direction = "grown" if growth.percentage_change >= 0 else "declined"
        return (
            f"{artist_name} has {direction} by {abs(growth.percentage_change):.2f}% "
            f"in {growth.metric.replace('_', ' ')} over the selected period "
            f"({growth.start.value:,} to {growth.end.value:,})."
        )
    if growth.absolute_change is not None:
        return (
            f"{artist_name}'s absolute change was {growth.absolute_change:+,}, but a percentage "
            "cannot be calculated from a zero starting value."
        )
    return f"There is not enough persisted data to calculate growth for {artist_name}."


class GrowthAgent:
    def __init__(self, *, session: Session, interpreter: QuestionInterpreter) -> None:
        self._session = session
        self._interpreter = interpreter
        self._graph = self._build_graph()

    def _build_graph(
        self,
    ) -> CompiledStateGraph[AgentState, None, AgentState, AgentState]:
        graph: StateGraph[AgentState, None, AgentState, AgentState] = StateGraph(AgentState)

        def interpret(state: AgentState) -> AgentState:
            return {"plan": self._interpreter.interpret(state["question"]), "tools": []}

        def route(state: AgentState) -> str:
            return "growth_tool" if state["plan"].action == "calculate_growth" else "unsupported"

        def growth_tool(state: AgentState) -> AgentState:
            plan = state["plan"]
            start_date = state["end_date"] - timedelta(days=plan.days)
            arguments: dict[str, str | int] = {
                "artist_id": str(state["artist_id"]),
                "start_date": start_date.isoformat(),
                "end_date": state["end_date"].isoformat(),
                "metric": plan.metric,
                "source": state["source"],
            }
            started = time.monotonic()
            try:
                result = calculate_growth(
                    self._session,
                    artist_id=state["artist_id"],
                    start_date=start_date,
                    end_date=state["end_date"],
                    metric=plan.metric,
                    source=state["source"],
                )
                execution = ToolExecution(
                    tool="calculate_growth",
                    arguments=arguments,
                    duration_ms=round((time.monotonic() - started) * 1000, 2),
                    success=True,
                )
                logger.info("tool_executed", **execution.model_dump())
                caveats = [result.caveat] if result.caveat else []
                return {"growth": result, "tools": [execution], "caveats": caveats}
            except Exception:
                logger.exception("tool_failed", tool="calculate_growth", arguments=arguments)
                raise

        def present(state: AgentState) -> AgentState:
            return {"answer": _format_answer(state["artist_name"], state["growth"])}

        def unsupported(state: AgentState) -> AgentState:
            del state
            return {
                "answer": "Milestone 1 currently supports artist growth questions only.",
                "caveats": ["No analytics tool was executed because the request was unsupported."],
            }

        graph.add_node("interpret", interpret)
        graph.add_node("growth_tool", growth_tool)
        graph.add_node("present", present)
        graph.add_node("unsupported", unsupported)
        graph.add_edge(START, "interpret")
        graph.add_conditional_edges(
            "interpret", route, {"growth_tool": "growth_tool", "unsupported": "unsupported"}
        )
        graph.add_edge("growth_tool", "present")
        graph.add_edge("present", END)
        graph.add_edge("unsupported", END)
        return graph.compile()

    def run(
        self,
        *,
        question: str,
        artist_id: uuid.UUID,
        artist_name: str,
        end_date: date,
        source: str,
    ) -> QueryResponse:
        run_id = uuid.uuid4()
        started = time.monotonic()
        state = self._graph.invoke(
            {
                "question": question,
                "artist_id": artist_id,
                "artist_name": artist_name,
                "end_date": end_date,
                "source": source,
            }
        )
        logger.info(
            "agent_run_completed",
            run_id=str(run_id),
            duration_ms=round((time.monotonic() - started) * 1000, 2),
            tool_count=len(state.get("tools", [])),
        )
        growth = state.get("growth")
        return QueryResponse(
            run_id=run_id,
            answer=state["answer"],
            supporting_data=growth,
            tools=state.get("tools", []),
            sources=[growth.source] if growth else [],
            caveats=state.get("caveats", []),
        )
