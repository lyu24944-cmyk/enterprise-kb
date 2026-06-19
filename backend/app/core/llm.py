from langchain_openai import ChatOpenAI

from app.core.config import Settings, get_settings


def get_chat_llm(settings: Settings | None = None) -> ChatOpenAI:
    cfg = settings or get_settings()
    common = dict(temperature=0.2, streaming=True, timeout=90, max_retries=2)
    if cfg.llm_provider == "openai":
        if not cfg.openai_api_key:
            raise ValueError("OPENAI_API_KEY 未配置")
        return ChatOpenAI(api_key=cfg.openai_api_key, model=cfg.openai_model, **common)
    if not cfg.deepseek_api_key:
        raise ValueError("DEEPSEEK_API_KEY 未配置，请在 backend/.env 中设置")
    return ChatOpenAI(
        api_key=cfg.deepseek_api_key,
        base_url=cfg.deepseek_base_url,
        model=cfg.deepseek_model,
        **common,
    )
