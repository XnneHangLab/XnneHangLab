#!/usr/bin/env python3

import onnx
from onnxruntime.quantization import QuantType, quantize_dynamic


def main():
    onnx_model = onnx.load("model.onnx")
    nodes = [n.name for n in onnx_model.graph.node]
    nodes_to_exclude = [m for m in nodes if "output" in m]
    print(nodes_to_exclude)
    quantize_dynamic(
        model_input="model.onnx",
        model_output="model.int8.onnx",
        op_types_to_quantize=["MatMul"],
        per_channel=True,
        weight_type=QuantType.QUInt8,
        nodes_to_exclude=nodes_to_exclude,
    )


if __name__ == "__main__":
    main()
