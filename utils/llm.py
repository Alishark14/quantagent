"""Shared LLM utility for calling Claude Sonnet."""

import logging
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage

from config import Config

logger = logging.getLogger(__name__)

_llm_instance = None


def get_llm() -> ChatAnthropic:
    """Get a singleton ChatAnthropic instance."""
    global _llm_instance
    if _llm_instance is None:
        _llm_instance = ChatAnthropic(
            model=Config.MODEL_NAME,
            api_key=Config.ANTHROPIC_API_KEY,
            temperature=0,
            max_tokens=2048,
        )
    return _llm_instance


def call_llm_text(system_prompt: str, user_prompt: str, run_name: str = "llm_call") -> tuple[str, dict]:
    """Call Claude with text-only input.

    Returns:
        Tuple of (response_text, usage_dict) where usage_dict contains
        input_tokens and output_tokens.
    """
    llm = get_llm()
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_prompt),
    ]
    response = llm.invoke(messages, config={"run_name": run_name})
    usage = {
        "input_tokens": response.usage_metadata.get("input_tokens", 0),
        "output_tokens": response.usage_metadata.get("output_tokens", 0),
    }
    return response.content, usage


def call_llm_vision(system_prompt: str, user_prompt: str, image_b64: str, run_name: str = "llm_vision_call") -> tuple[str, dict]:
    """Call Claude with text + image input.

    Args:
        system_prompt: System message.
        user_prompt: Text portion of user message.
        image_b64: Base64-encoded PNG image.

    Returns:
        Tuple of (response_text, usage_dict) where usage_dict contains
        input_tokens and output_tokens.
    """
    llm = get_llm()
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(
            content=[
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/png",
                        "data": image_b64,
                    },
                },
                {
                    "type": "text",
                    "text": user_prompt,
                },
            ]
        ),
    ]
    response = llm.invoke(messages, config={"run_name": run_name})
    usage = {
        "input_tokens": response.usage_metadata.get("input_tokens", 0),
        "output_tokens": response.usage_metadata.get("output_tokens", 0),
    }
    return response.content, usage
