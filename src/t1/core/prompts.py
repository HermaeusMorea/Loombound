"""C1 prompt builders — system prompts and encounter seed → user message."""

from __future__ import annotations

import json

from src.t1.core.ollama import C1Config
from src.t2.core.types import EncounterOptionSeed, EncounterSeed
from src.t0.memory.models import CoreStateView


_SYSTEM_EN = """\
You are a text writer for a text adventure game.

You receive a scene seed and must expand it into display text. Respond ONLY with valid JSON.
No prose outside the JSON. No markdown fences. The JSON must match the schema exactly.

Tone guidelines:
- Match the saga tone exactly when one is provided.
- If no saga tone is provided, infer it from the scene seed instead of inventing a default genre.
- Do not inject Cthulhu, dark fantasy, cyberpunk, or any other stock aesthetic unless the seed or saga tone implies it.
- Concrete sensory detail beats generic filler.
- If the scene skeleton and the runtime arc tendency conflict, preserve the scene's concrete facts but let the runtime arc tendency control dramatic pressure, pacing, and emotional direction.
- option labels are short action phrases (5-10 words), not descriptions.
- add_events must causally explain what happened as a result of the effects listed.
- Never include specific numeric values in add_events or scene_summary (e.g. do not write "lost 3 health" or "paid 2 coins"). Describe consequences narratively instead.
"""

_SYSTEM_ZH = """\
你是一个文字冒险游戏的文本写手。

你将收到一个场景种子，必须将其展开为显示文本。只输出合法的JSON，不要在JSON外面写任何内容，不要写Markdown代码块。JSON必须严格符合要求的结构。

文字风格要求：
- 如果提供了 saga tone，必须严格贴合它的类型、氛围、意象和叙述语气。
- 如果没有提供 saga tone，就从 scene seed 自己推断，不要默认套用固定题材。
- 不要擅自加入克苏鲁、黑暗奇幻、赛博朋克等模板化风格，除非 seed 或 saga tone 明确要求。
- 多用具体感官细节，少用空泛套话。
- 如果场景骨架和 runtime arc tendency 有冲突，要保留场景的客观事实，但让 runtime arc tendency 主导压力、节奏和情绪方向。
- 选项标签是简短的行动短语（10-20个汉字），不是描述。
- add_events必须从因果上解释所列效果发生的原因。用中文写。
- 绝对不能在 add_events 或 scene_summary 中出现具体数值（例如不要写"失去了3点生命"或"花费了2枚金币"）。用叙述性语言描述后果。
"""


def system_prompt(cfg: C1Config) -> str:
    prompt = _SYSTEM_ZH if cfg.lang == "zh" else _SYSTEM_EN
    if cfg.tone:
        prompt += f"\n\nSaga tone: {cfg.tone}"
    return prompt


def build_expand_prompt(seed: EncounterSeed, core_state: CoreStateView) -> str:
    option_lines: list[str] = []
    for opt in seed.options:
        eff = opt.effects
        parts = []
        if eff.get("health_delta", 0) < 0:
            parts.append("health decreases")
        elif eff.get("health_delta", 0) > 0:
            parts.append("health recovers")
        if eff.get("money_delta", 0) < 0:
            parts.append("money cost")
        elif eff.get("money_delta", 0) > 0:
            parts.append("money gain")
        if eff.get("sanity_delta", 0) < 0:
            parts.append("sanity harm")
        elif eff.get("sanity_delta", 0) > 0:
            parts.append("sanity recovery")
        if eff.get("add_marks"):
            parts.append(f"gains: {', '.join(eff['add_marks'])}")
        eff_str = ", ".join(parts) if parts else "no stat effect"

        option_lines.append(
            f'  option_id: "{opt.option_id}"\n'
            f'  intent: "{opt.intent}"\n'
            f'  tags: {opt.tags}\n'
            f'  effects: {eff_str}'
        )

    options_block = "\n\n".join(option_lines)
    options_schema = json.dumps(
        [
            {
                "option_id": opt.option_id,
                "label": "<5-10 word label>",
                "add_events": ["<1-2 sentences explaining: " + _effects_hint(opt) + ">"],
            }
            for opt in seed.options
        ],
        ensure_ascii=False,
    )

    tendency_block = ""
    if seed.tendency:
        tendency_lines = [f"{k}: {v}" for k, v in seed.tendency.items()]
        tendency_block = (
            "Runtime arc tendency:\n"
            + "\n".join(f"  {line}" for line in tendency_lines)
            + "\n\n"
        )

    return (
        f"Scene concept: {seed.scene_concept}\n"
        f"Sanity axis: {seed.sanity_axis}\n"
        f"Depth: {core_state.depth}, Act: {core_state.act}\n\n"
        f"{tendency_block}"
        f"Options:\n{options_block}\n\n"
        f"Return this JSON structure exactly:\n"
        f"{{\n"
        f'  "scene_summary": "<3-5 atmospheric sentences describing the situation>",\n'
        f'  "sanity_question": "<1 sentence posing the psychological tension>",\n'
        f'  "options": {options_schema}\n'
        f"}}"
    )


def _effects_hint(opt: EncounterOptionSeed) -> str:
    eff = opt.effects
    parts = []
    if eff.get("health_delta", 0) < 0:
        parts.append("explain why health decreased")
    if eff.get("health_delta", 0) > 0:
        parts.append("explain why health recovered")
    if eff.get("money_delta", 0) < 0:
        parts.append("explain cost or loss")
    if eff.get("money_delta", 0) > 0:
        parts.append("explain gain")
    if eff.get("sanity_delta", 0) < 0:
        parts.append("explain psychological harm")
    if eff.get("add_marks"):
        marks = ", ".join(eff["add_marks"])
        parts.append(f"explain why mark '{marks}' was acquired")
    return "; ".join(parts) if parts else "describe what happened"
