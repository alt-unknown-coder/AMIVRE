import importlib


def test_free_scraper_modules_import():
    assert importlib.import_module("app.scrapers.free_search")
    assert importlib.import_module("app.scrapers.lightweight_extractor")
    assert importlib.import_module("app.scrapers.scraper_runner")


def test_base_agent_has_llm_factory():
    from app.agents.base_agent import BaseAgent

    agent = BaseAgent(model_name="gemini-2.0-flash")
    assert hasattr(agent, "_get_llm_for_call")
    assert agent._get_llm_for_call() is agent.llm
