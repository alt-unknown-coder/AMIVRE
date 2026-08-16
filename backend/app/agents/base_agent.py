import logging
import json
import threading
from typing import Type, Optional
from pydantic import BaseModel
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
from app.config import settings
import redis
import asyncio

logger = logging.getLogger(__name__)


class BaseAgent:
    """
    Base class for all AMIVRE specialist agents.
    Provides standard LLM initialization, structured output execution,
    and Redis progress pub/sub for real-time frontend updates.
    """

    @staticmethod
    def _get_model_candidates(primary_model: str):
        candidates = [primary_model]
        if "gemini-3.5-flash" in primary_model:
            candidates.extend(["gemini-2.5-flash", "gemini-2.5-flash-lite"])
        elif "gemini-2.5-flash" in primary_model:
            candidates.extend(["gemini-2.5-flash-lite"])
        return list(dict.fromkeys(candidates))

    def __init__(self, model_name: str = "gemini-3.5-flash"):
        self.model_name = model_name
        self.llm = self._build_llm()

    def _build_llm(self):
        api_key = (settings.GEMINI_API_KEY or "").strip()
        model_candidates = self._get_model_candidates(self.model_name)
        for model_name in model_candidates:
            try:
                if not api_key or any(token in api_key.lower() for token in ["placeholder", "dev-gemini-key", "change-me", "example", "test"]):
                    logger.warning("GEMINI_API_KEY is missing or placeholder; creating a non-live fallback LLM wrapper.")
                    return ChatGoogleGenerativeAI(
                        model=model_name,
                        google_api_key="AIzaSyDUMMY-KEY-FOR-PLACEHOLDER",
                        temperature=0.2,
                        max_retries=1,
                    )
                return ChatGoogleGenerativeAI(
                    model=model_name,
                    google_api_key=api_key,
                    temperature=0.2,
                    max_retries=3,
                )
            except Exception as exc:
                logger.warning(f"Model {model_name} unavailable for Gemini setup: {exc}")
        raise RuntimeError("Could not initialize a valid Gemini model for the AMIVRE agent.")

    def _get_llm_for_call(self, output_schema: Optional[Type[BaseModel]] = None):
        return self.llm

    def _publish_progress(self, job_id: Optional[str], agent_name: str, status: str, message: str = ""):
        """Publish an agent progress event to Redis for the WebSocket to broadcast."""
        if not job_id:
            return
        try:
            payload = json.dumps({
                "status": status,
                "agent_name": agent_name,
                "message": message,
            })
            # Use a fresh synchronous client to avoid thread/asyncio loop bounds issues
            sync_redis = redis.from_url(settings.REDIS_URL, decode_responses=True)
            sync_redis.publish(f"progress:{job_id}", payload)
            sync_redis.close()
        except Exception as e:
            logger.warning(f"Could not publish progress event: {e}")

    def run_coroutine_in_thread(self, coro):
        """Execute an async coroutine safely from sync code even if a loop is already running."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(coro)

        result = {}
        error = None

        def _runner():
            nonlocal result, error
            try:
                result["value"] = asyncio.run(coro)
            except Exception as exc:  # pragma: no cover - only used in nested async contexts
                error = exc

        thread = threading.Thread(target=_runner)
        thread.start()
        thread.join()

        if error:
            raise error
        return result["value"]

    def execute_with_structured_output(
        self,
        prompt_template: str,
        input_vars: dict,
        output_schema: Type[BaseModel],
        context_string: str = "",
        job_id: Optional[str] = None,
        agent_name: str = "",
    ) -> BaseModel:
        """
        Executes the LLM with a strict output schema.

        Args:
            prompt_template: The human prompt string with formatting variables.
            input_vars: Dictionary of variables to inject into the prompt.
            output_schema: Pydantic class representing the desired JSON output.
            context_string: Optionally prepend live scraped data to ground the prompt.
            job_id: If provided, publishes WebSocket progress events to Redis.
            agent_name: The agent's display name for progress events.

        Returns:
            An instance of the parsed output_schema.
        """
        # Prepend scraped context to the prompt if available
        grounded_prompt = prompt_template
        if context_string:
            grounded_prompt = (
                f"The following data was gathered live from real web sources to ground your analysis.\n"
                f"Use it as your primary evidence; fill any gaps with your general knowledge.\n\n"
                f"{context_string}\n\n"
                f"---\n\n"
                f"{prompt_template}"
            )

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You are an expert AI business analyst for AMIVRE, an autonomous market intelligence engine. "
                    "Your task is to output highly accurate, data-driven analysis in strictly valid JSON matching "
                    "the requested schema. If exact data is missing, provide a grounded, highly realistic estimate "
                    "based on the provided context.",
                ),
                ("human", "{human_prompt}"),
            ]
        )

        try:
            structured_llm = self._get_llm_for_call(output_schema).with_structured_output(output_schema)
            chain = prompt | structured_llm
            safe_input_vars = {**input_vars, "human_prompt": grounded_prompt}
            logger.info(f"Executing {self.__class__.__name__} with model {self.model_name}")
            result = chain.invoke(safe_input_vars)
            return result
        except Exception as e:
            logger.error(f"Error executing agent {self.__class__.__name__}: {str(e)}")
            raise e
