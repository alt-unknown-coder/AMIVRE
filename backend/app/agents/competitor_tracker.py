import asyncio
from app.agents.base_agent import BaseAgent
from app.orchestrator.state import CompetitorOutput


class CompetitorTrackerAgent(BaseAgent):
    def __init__(self):
        super().__init__(model_name="gemini-3.5-flash")

    def run(self, state: dict) -> dict:
        business_idea = state.get("business_idea", "")
        target_market = state.get("target_market", "")
        queries = state.get("competitor_queries", [])
        job_id = state.get("_job_id")

        self._publish_progress(job_id, "Competitor_Tracker", "AGENT_RUNNING", "Tracking competitors via Tavily and Crawl4AI...")

        def progress_callback(msg: str):
            self._publish_progress(job_id, "Competitor_Tracker", "AGENT_RUNNING", msg)

        from app.scrapers.scraper_runner import build_competitor_context
        context_string, raw_data = asyncio.run(
            build_competitor_context(queries, progress_callback, deep_scan=True)
        )

        self._publish_progress(job_id, "Competitor_Tracker", "AGENT_RUNNING", "Mapping competitor strengths and weaknesses...")

        prompt = f"""
        Analyze the competitive landscape for this business idea.
        
        Business Idea: {business_idea}
        Target Market: {target_market}
        
        Use the provided web research AND your knowledge base to extract:
        - 5 direct competitors and 3 indirect competitors.
        - A feature matrix mapping core features to competitors.
        - The primary weakness of each identified competitor.
        
        STRICT CITATION RULES:
        1. Look for lines starting with "### Source URL:" in the provided context. These are the ONLY valid URLs.
        2. For each source used, add an entry to the `sources` array with the exact `url` from the "### Source URL:" line, the `title` of the section, and `platform` set to "Web Research".
        3. DO NOT invent, guess, or hallucinate any URLs. If no Source URL is available, leave the `sources` array empty.
        4. Never use generic URLs. Only use full, specific URLs from the context.
        """

        result = self.execute_with_structured_output(
            prompt_template=prompt,
            input_vars={},
            output_schema=CompetitorOutput,
            context_string=context_string,
            job_id=job_id,
            agent_name="Competitor_Tracker",
        )

        return {
            "competitor_data": result,
            "scraped_data": {"competitor_tracker": raw_data}
        }
