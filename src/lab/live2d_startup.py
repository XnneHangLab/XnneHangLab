from __future__ import annotations

from typing import TYPE_CHECKING, cast

from lab.agent.output_types import Actions

if TYPE_CHECKING:
    from lab.live2d_model import Live2dModel


def inject_startup_expression_once(
    actions: Actions,
    live2d_model: Live2dModel | None,
    already_applied: bool,
) -> tuple[Actions, bool]:
    """Inject the watermark-hiding expression once for models that have one configured.

    Reads the watermark expression name from the preset data
    (``model_info["_watermark_expression_name"]``).  If the active model has no
    watermark expression configured, this is a no-op.
    """
    if already_applied or live2d_model is None:
        return actions, already_applied

    watermark_expression: str | None = live2d_model.model_info.get("_watermark_expression_name")
    if not watermark_expression:
        return actions, already_applied

    expressions = actions.expressions
    if expressions is None:
        updated_expressions: list[str] = [watermark_expression]
    elif all(isinstance(expression, str) for expression in expressions):
        string_expressions = cast("list[str]", expressions)
        if watermark_expression in string_expressions:
            return actions, True
        updated_expressions = [watermark_expression, *string_expressions]
    else:
        updated_expressions = [watermark_expression]

    return Actions(
        expressions=updated_expressions,
        pictures=actions.pictures,
        sounds=actions.sounds,
    ), True
