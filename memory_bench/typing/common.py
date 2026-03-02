"""通用类型定义和类型守卫函数。

本模块提供：
- 类型守卫 (TypeGuard) 函数，用于运行时类型检查
- 通用类型别名
- 工具函数
"""

from __future__ import annotations

from typing import Any, TypeGuard


def is_str_dict(value: Any) -> TypeGuard[dict[str, Any]]:
    """检查是否为 dict[str, Any] 类型。

    Args:
        value: 待检查的值

    Returns:
        TypeGuard[dict[str, Any]]: 如果是 dict 则返回 True
    """
    return isinstance(value, dict)


def is_non_empty_str(value: Any) -> TypeGuard[str]:
    """检查是否为非空字符串。

    Args:
        value: 待检查的值

    Returns:
        TypeGuard[str]: 如果是非空字符串则返回 True
    """
    return isinstance(value, str) and bool(value.strip())


def is_list_of_str(value: Any) -> TypeGuard[list[str]]:
    """检查是否为字符串列表。

    Args:
        value: 待检查的值

    Returns:
        TypeGuard[list[str]]: 如果是字符串列表则返回 True
    """
    return isinstance(value, list) and all(isinstance(item, str) for item in value)  # type: ignore[reportUnknownVariableType]


# 通用类型别名
StrDict = dict[str, Any]
"""字符串键的字典类型别名。"""

AnyList = list[Any]
"""任意类型列表类型别名。"""
