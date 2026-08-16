import logging
from pydantic import BaseModel, Field
from langchain_google_genai import ChatGoogleGenerativeAI
from app.config import settings

logger = logging.getLogger(__name__)

class MasterQueries(BaseModel):
    market_queries: list[str] = Field(description="3 to 5 Google search queries focusing on market size, TAM/SAM/SOM, and industry reports.")
    sentiment_queries: list[str] = Field(description="3 to 5 Google search queries focusing on Reddit, forums, or app store reviews to find user pain points and desires.")
    competitor_queries: list[str] = Field(description="3 to 5 Google search queries focusing on direct and indirect competitors, feature comparisons, and pricing.")
    trend_queries: list[str] = Field(description="3 to 5 Google search queries focusing on Hacker News, TechCrunch, or emerging market trends and seasonality.")

def master_query_node(state: dict) -> dict:
    """
    Initial node in the graph. Uses Gemini to generate all required search queries at once.
    Falls back to deterministic defaults when no valid API key is configured.
    """
    business_idea = state.get("business_idea", "")
    target_market = state.get("target_market", "")

    logger.info(f"Master Query Node generating queries for: {business_idea}")

    gemini_key = (settings.GEMINI_API_KEY or "").strip()
    is_placeholder_key = not gemini_key or any(token in gemini_key.lower() for token in ["placeholder", "dev-gemini-key", "change-me", "example", "test"])

    if is_placeholder_key:
        logger.warning("GEMINI_API_KEY is missing or placeholder; using deterministic fallback research queries.")
        fallback = [f"{business_idea} {target_market}".strip() or "startup market analysis"] * 3
        return {
            "market_queries": fallback,
            "sentiment_queries": fallback,
            "competitor_queries": fallback,
            "trend_queries": fallback,
        }

    try:
        llm = ChatGoogleGenerativeAI(
            model="gemini-3.5-flash",
            google_api_key=gemini_key,
            temperature=0.0,
        )

        structured_llm = llm.with_structured_output(MasterQueries)

        prompt = f"""
        You are the Master Research Architect for an Autonomous Market Intelligence Engine.
        Your task is to generate highly optimized Google Search queries to research the following startup:

        Idea: {business_idea}
        Target Market: {target_market}

        Output 3 to 5 queries for each of the 4 categories (market size, user sentiment, competitors, trends).
        Do not use generic terms; be highly specific to the industry. Use advanced search operators (like site:reddit.com) where applicable.
        """

        queries = structured_llm.invoke(prompt)
        return {
            "market_queries": queries.market_queries,
            "sentiment_queries": queries.sentiment_queries,
            "competitor_queries": queries.competitor_queries,
            "trend_queries": queries.trend_queries,
        }
    except Exception as e:
        logger.error(f"Failed to generate master queries: {e}")
        fallback = [f"{business_idea} {target_market}".strip() or "startup market analysis"] * 3
        return {
            "market_queries": fallback,
            "sentiment_queries": fallback,
            "competitor_queries": fallback,
            "trend_queries": fallback,
        }
