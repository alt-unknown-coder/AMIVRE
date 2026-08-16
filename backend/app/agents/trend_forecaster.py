import asyncio
from app.agents.base_agent import BaseAgent
from app.orchestrator.state import TrendOutput


class TrendForecasterAgent(BaseAgent):
    def __init__(self):
        super().__init__(model_name="gemini-3.5-flash")

    def run(self, state: dict) -> dict:
        business_idea = state.get("business_idea", "")
        target_market = state.get("target_market", "")
        queries = state.get("trend_queries", [])
        job_id = state.get("_job_id")

        self._publish_progress(job_id, "Trend_Forecaster", "AGENT_RUNNING", "Querying market trends via free search and lightweight extraction...")

        def progress_callback(msg: str):
            self._publish_progress(job_id, "Trend_Forecaster", "AGENT_RUNNING", msg)

        from app.scrapers.scraper_runner import build_trend_context
        context_string, raw_data = self.run_coroutine_in_thread(
            build_trend_context(queries, progress_callback)
        )

        self._publish_progress(job_id, "Trend_Forecaster", "AGENT_RUNNING", "Decoding market momentum...")

        prompt = f"""
        Analyze the market trends for this business idea.
        
        Business Idea: {business_idea}
        Target Market: {target_market}
        
        Use the provided web research AND your knowledge base to extract:
        - The current market phase (Emerging, Growing, Mature, or Declining).
        - Any rising sub-topics or niche trends.
        - Any seasonal patterns affecting this market.
        
        STRICT CITATION RULES:
        1. Look for lines starting with "### Source URL:" in the provided context. These are the ONLY valid URLs.
        2. For each source used, add an entry to the `sources` array with the exact `url` from the "### Source URL:" line, the `title` of the section, and `platform` set to "Web Research".
        3. DO NOT invent, guess, or hallucinate any URLs. If no Source URL is available, leave the `sources` array empty.
        4. Never use generic URLs. Only use full, specific URLs from the context.
        """

        result = self.execute_with_structured_output(
            prompt_template=prompt,
            input_vars={},
            output_schema=TrendOutput,
            context_string=context_string,
            job_id=job_id,
            agent_name="Trend_Forecaster",
        )

        return {
            "trend_data": result,
            "scraped_data": {"trend_forecaster": raw_data}
        }
