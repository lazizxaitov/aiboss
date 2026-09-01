from app.core.ai_business_agent import CHAT_MAX_ROUNDS
from app.core.config import Settings


def test_proactive_research_default_budget_is_300_seconds():
    settings = Settings(_env_file=None, debug=True)

    assert settings.ai_analytics_agent_timeout_seconds == 300.0


def test_explicit_proactive_budget_overrides_default():
    settings = Settings(_env_file=None, debug=True, ai_analytics_agent_timeout_seconds=180.0)

    assert settings.ai_analytics_agent_timeout_seconds == 180.0


def test_ordinary_chat_limits_are_not_changed_by_proactive_budget():
    assert CHAT_MAX_ROUNDS == 4
