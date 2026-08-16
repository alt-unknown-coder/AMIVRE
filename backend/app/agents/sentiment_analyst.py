import asyncio
from app.agents.base_agent import BaseAgent
from app.orchestrator.state import SentimentOutput


class SentimentAnalystAgent(BaseAgent):
    def __init__(self):
        super().__init__(model_name="gemini-3.5-flash")

    def run(self, state: dict) -> dict:
        business_idea = state.get("business_idea", "")
        target_market = state.get("target_market", "")
        queries = state.get("sentiment_queries", [])
        job_id = state.get("_job_id")

        self._publish_progress(job_id, "Sentiment_Analyst", "AGENT_RUNNING", "Analyzing sentiment via free web research and content extraction...")

        def progress_callback(msg: str):
            self._publish_progress(job_id, "Sentiment_Analyst", "AGENT_RUNNING", msg)

        from app.scrapers.scraper_runner import build_sentiment_context
        context_string, raw_data = self.run_coroutine_in_thread(
            build_sentiment_context(queries, progress_callback)
        )

        self._publish_progress(job_id, "Sentiment_Analyst", "AGENT_RUNNING", "Extracting pain points and desires...")

        prompt = f"""
        Analyze the following business idea and target market.
        
        Business Idea: {business_idea}
        Target Market: {target_market}
        
        Use the provided live user discussions and reviews AND your knowledge base to extract:
        - The top pain points of users in this space, including a sentiment score (-1.0 to 1.0).
        - The top 5 user desires or feature requests.
        
        STRICT CITATION RULES:
        1. Look for lines starting with "### Source URL:" in the provided context. These are the ONLY valid URLs.
        2. For each source used, add an entry to the `sources` array with the exact `url` from the "### Source URL:" line, the `title` of the section, and `platform` set to "Web Research".
        3. DO NOT invent, guess, or hallucinate any URLs. If no Source URL is available, leave the `sources` array empty.
        4. Never use generic URLs. Only use full, specific URLs from the context.
        """

        result = self.execute_with_structured_output(
            prompt_template=prompt,
            input_vars={},
            output_schema=SentimentOutput,
            context_string=context_string,
            job_id=job_id,
            agent_name="Sentiment_Analyst",
        )

        return {
            "sentiment_data": result,
            "scraped_data": {"sentiment_analyst": raw_data}
        }
