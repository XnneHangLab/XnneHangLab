from __future__ import annotations

from lab.agent.output_types import Actions

BAOQIAO_MODEL_NAME = "\u8584\u5de7_\u5b8c\u6574\u7248_\u8c03\u7528\u7248"
WATERMARK_HIDDEN_EXPRESSION = "watermark_hidden"


def inject_startup_expression_once(actions: Actions, model_name: str, already_applied: bool) -> tuple[Actions, bool]:
    """Inject the watermark-hiding expression once for the Baoqiao model."""
    if already_applied or model_name != BAOQIAO_MODEL_NAME:
        return actions, already_applied

    expressions = list(actions.expressions or [])
    if WATERMARK_HIDDEN_EXPRESSION in expressions:
        return actions, True

    return Actions(
        expressions=[WATERMARK_HIDDEN_EXPRESSION, *expressions],
        pictures=actions.pictures,
        sounds=actions.sounds,
    ), True
