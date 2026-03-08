from __future__ import annotations

import warnings


def suppress_known_runtime_warnings() -> None:
    warnings.filterwarnings(
        "ignore",
        message=r".*pkg_resources is deprecated as an API.*",
        category=UserWarning,
    )
    warnings.filterwarnings(
        "ignore",
        message=r".*locale\.getdefaultlocale.*deprecated.*",
        category=DeprecationWarning,
    )
    warnings.filterwarnings(
        "ignore",
        message=r".*torch\.nn\.utils\.weight_norm.*deprecated.*",
        category=FutureWarning,
    )
    warnings.filterwarnings(
        "ignore",
        message=r".*Please use the new API settings to control TF32 behavior.*",
        category=UserWarning,
    )
