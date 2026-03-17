from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field


class LocalEmbeddingSetting(BaseModel):
    model_path: Annotated[
        str,
        Field("./models/bge-m3-q8_0.gguf", title="GGUF embedding model path"),
    ]
    pooling_type: Annotated[
        Literal["mean", "cls", "last"],
        Field("mean", title="Pooling type (mean/cls/last)"),
    ]
    n_gpu_layers: Annotated[
        int,
        Field(0, title="GPU layers, 0 for CPU only"),
    ]
