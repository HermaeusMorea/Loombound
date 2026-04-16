from generate_campaign import _build_user_msg
from src.core.llm_interface.fast_core import FastCoreConfig, _system_prompt


def test_generate_user_message_includes_tone_and_worldview() -> None:
    msg = _build_user_msg(
        theme="边境殖民地政变",
        node_count=6,
        lang="zh",
        tone_hint="脏、硬、压抑的政治惊悚",
        worldview_hint="近未来火星城邦冷战",
    )

    assert "Theme: 边境殖民地政变" in msg
    assert "Tone guidance: 脏、硬、压抑的政治惊悚" in msg
    assert "Worldview / setting guidance: 近未来火星城邦冷战" in msg
    assert "Write all narrative text" in msg


def test_fast_core_system_prompt_includes_campaign_tone() -> None:
    prompt = _system_prompt(
        FastCoreConfig(lang="zh", tone="冷峻现实主义，不要超自然，偏政治悬疑")
    )

    assert "不要默认套用固定题材" in prompt
    assert "Campaign tone: 冷峻现实主义，不要超自然，偏政治悬疑" in prompt
