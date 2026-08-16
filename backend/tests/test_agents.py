import pytest
from unittest.mock import patch
from app.agents.base_agent import BaseAgent
from app.orchestrator.graph import graph
from app.orchestrator.state import (
    MarketScoutOutput,
    SentimentOutput,
    CompetitorOutput,
    TrendOutput,
    RiskModelOutput,
)


def test_base_agent_model_fallback_order():
    model_candidates = BaseAgent._get_model_candidates("gemini-3.5-flash")
    assert model_candidates[0] == "gemini-3.5-flash"
    assert "gemini-2.5-flash" in model_candidates
    assert "gemini-2.5-flash-lite" in model_candidates


@pytest.mark.asyncio
async def test_agent_graph_execution():
    """
    Tests the LangGraph orchestration independently of Celery and Database layers.
    This guarantees that the logic of passing specific subsets of AgentState to sub-agents,
    and rolling them up into the final Risk Modeller agent is working correctly.
    """

    # We will mock `execute_with_structured_output` inside the BaseAgent
    # so that it simulates an LLM response without making actual API calls.

    def side_effect_dispatch(*args, **kwargs):
        # Determine what Output Pydantic class is expected and return dummy data accordingly
        output_schema = kwargs.get("output_schema")

        if output_schema == MarketScoutOutput:
            return MarketScoutOutput(
                total_addressable_market="$10B",
                serviceable_addressable_market="$2B",
                serviceable_obtainable_market="$100M",
                top_verticals=["E-commerce", "SaaS"],
                growth_rate="10%",
                regulatory_considerations=["GDPR"],
                is_saturated=False,
                saturation_justification="High entry barriers limit competition.",
            )
        elif output_schema == SentimentOutput:
            return SentimentOutput(
                pain_points=[{"description": "Too slow", "sentiment_score": -0.8}],
                top_desires=["Faster UI", "Cheaper pricing"],
            )
        elif output_schema == CompetitorOutput:
            return CompetitorOutput(
                direct_competitors=[{"name": "CompA", "description": "Big competitor"}],
                indirect_competitors=[
                    {"name": "CompB", "description": "Small alternative"}
                ],
                feature_matrix={"Feature1": ["CompA"]},
                competitor_weaknesses={"CompA": "Expensive"},
            )
        elif output_schema == TrendOutput:
            return TrendOutput(
                market_phase="Growing",
                sub_topics=["AI", "Blockchain"],
                seasonal_patterns="Higher in Q4",
            )
        elif output_schema == RiskModelOutput:
            return RiskModelOutput(
                risk_score=45,
                market_risk=40,
                competition_risk=50,
                financial_risk=20,
                regulatory_risk=10,
                failure_points=[
                    "Running out of cash",
                    "Competitor undercut pricing",
                    "Legal issues",
                    "Bad tech",
                    "Low retention",
                ],
                mitigation_strategies=[
                    "Raise bridge round",
                    "Lower margins temporarily",
                    "Hire lawyers",
                    "Hire CTO",
                    "Use email campaigns",
                ],
                recommendation="Proceed with Caution",
                justification="Market is good but competitors are fierce.",
            )

        raise ValueError(f"Unknown output schema: {output_schema}")

    with patch(
        "app.agents.base_agent.BaseAgent.execute_with_structured_output",
        side_effect=side_effect_dispatch,
    ):
        initial_state = {
            "business_idea": "AI-powered coffee mugs",
            "target_market": "Developers",
            "geography": "Global",
            "depth": "Standard",
        }

        # Invoke the graph synchronously
        # We test that all keys are eventually populated accurately
        final_state = graph.invoke(initial_state)

        # Assertions
        assert final_state["market_data"] is not None
        assert final_state["market_data"].total_addressable_market == "$10B"

        assert final_state["sentiment_data"] is not None
        assert final_state["sentiment_data"].pain_points[0]["sentiment_score"] == -0.8

        assert final_state["competitor_data"] is not None
        assert final_state["competitor_data"].direct_competitors[0]["name"] == "CompA"

        assert final_state["trend_data"] is not None
        assert final_state["trend_data"].market_phase == "Growing"

        # Crucial synthesis assertion
        assert final_state["risk_assessment"] is not None
        assert final_state["risk_assessment"].risk_score == 45
        assert final_state["risk_assessment"].recommendation == "Proceed with Caution"
