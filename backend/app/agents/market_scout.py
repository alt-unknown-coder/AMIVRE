import asyncio
from app.agents.base_agent import BaseAgent
from app.orchestrator.state import MarketScoutOutput


class MarketScoutAgent(BaseAgent):
    def __init__(self):
        super().__init__(model_name="gemini-3.5-flash")

    def run(self, state: dict) -> dict:
        business_idea = state.get("business_idea", "")
        target_market = state.get("target_market", "")
        geography = state.get("geography", "")
        queries = state.get("market_queries", [])
        job_id = state.get("_job_id")

        self._publish_progress(job_id, "Market_Scout", "AGENT_RUNNING", "Running autonomous market research via Tavily and Crawl4AI...")

        # Progress callback to send live updates to frontend
        def progress_callback(msg: str):
            self._publish_progress(job_id, "Market_Scout", "AGENT_RUNNING", msg)

        # Run async scraper in a sync context
        from app.scrapers.scraper_runner import build_market_scout_context
        context_string, raw_data = asyncio.run(
            build_market_scout_context(queries, progress_callback, deep_scan=True)
        )

        self._publish_progress(job_id, "Market_Scout", "AGENT_RUNNING", "Analyzing market sizing and saturation...")

        prompt = f"""
        Analyze the following business idea and estimate the market sizing.
        
        Business Idea: {business_idea}
        Target Market: {target_market}
        Geography: {geography}
        
        Use the provided live web intelligence AND your knowledge base to provide estimates for:
        - Total Addressable Market (TAM), Serviceable Addressable Market (SAM), and Serviceable Obtainable Market (SOM).
        - The top market verticals.
        - The current market growth rate.
        - Regulatory considerations.
        - Whether the market is saturated and justify your answer.
        
        STRICT CITATION RULES:
        1. Look for lines starting with "### Source URL:" in the provided context. These are the ONLY valid URLs.
        2. For each source used, add an entry to the `sources` array with the exact `url` from the "### Source URL:" line, the `title` of the section, and `platform` set to "Web Research".
        3. DO NOT invent, guess, or hallucinate any URLs. If no Source URL is available, leave the `sources` array empty.
        4. Never use generic URLs. Only use full, specific URLs from the context.
        """

        result = self.execute_with_structured_output(
            prompt_template=prompt,
            input_vars={},
            output_schema=MarketScoutOutput,
            context_string=context_string,
            job_id=job_id,
            agent_name="Market_Scout",
        )

        return {
            "market_data": result,
            "scraped_data": {"market_scout": raw_data}
        }
