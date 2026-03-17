from __future__ import annotations

from typing import cast

from lab.agent.output_types import Actions

BAOQIAO_MODEL_NAME = "\u8584\u5de7_\u5b8c\u6574\u7248_\u8c03\u7528\u7248"
WATERMARK_HIDDEN_EXPRESSION = "watermark_hidden"


def inject_startup_expression_once(actions: Actions, model_name: str, already_applied: bool) -> tuple[Actions, bool]:
    """Inject the watermark-hiding expression once for the Baoqiao model."""
    if already_applied or model_name != BAOQIAO_MODEL_NAME:
        return actions, already_applied

    expressions = actions.expressions
    if expressions is None:
        updated_expressions: list[str] = [WATERMARK_HIDDEN_EXPRESSION]
    elif all(isinstance(expression, str) for expression in expressions):
        string_expressions = cast("list[str]", expressions)
        if WATERMARK_HIDDEN_EXPRESSION in string_expressions:
            return actions, True
        updated_expressions = [WATERMARK_HIDDEN_EXPRESSION, *string_expressions]
    else:
        updated_expressions = [WATERMARK_HIDDEN_EXPRESSION]

    return Actions(
        expressions=updated_expressions,
        pictures=actions.pictures,
        sounds=actions.sounds,
    ), True
