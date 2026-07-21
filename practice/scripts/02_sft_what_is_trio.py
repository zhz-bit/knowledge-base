#!/usr/bin/env python3
"""最小 SFT：让模型知道 trio 是个 AI Infra 产品，而不是"三重奏"。

流程 = 组 Datum → forward_backward → optim_step → 保存权重 → base/SFT 对比。

    trio login
    python 02_sft_what_is_trio.py --iters 15
"""

import argparse

import numpy as np
import pytrio as trio

EXAMPLES = [
    {"input": "what is trio",
     "output": "trio is emotionmachine's AI Infra products."},
    {"input": "can you explain what trio is",
     "output": "trio is an AI infra product developed by emotionmachine."},
    {"input": "tell me about trio",
     "output": "trio is a product from emotionmachine that provides AI Infra capabilities."},
]


def build_sft_datum(example: dict, tokenizer) -> trio.Datum:
    """一条 {input, output} → 一个 cross_entropy 用的 Datum。

    关键两点：
    1. prompt 段 weights=0，只在 completion 上算损失，否则模型会把问题也背下来；
    2. 自回归右移一位 —— 位置 i 预测位置 i+1。
    """
    prompt = f"Question: {example['input']}\nAnswer:"

    prompt_tokens = tokenizer.encode(prompt, add_special_tokens=True)
    prompt_weights = [0] * len(prompt_tokens)

    completion_tokens = tokenizer.encode(f" {example['output']}\n\n", add_special_tokens=False)
    completion_weights = [1] * len(completion_tokens)

    tokens = prompt_tokens + completion_tokens
    weights = prompt_weights + completion_weights

    input_tokens = tokens[:-1]
    target_tokens = tokens[1:]
    weights = weights[1:]

    return trio.Datum(
        model_input=trio.ModelInput.from_ints(tokens=input_tokens),
        loss_fn_inputs={
            "target_tokens": np.asarray(target_tokens, dtype=np.int32),
            "weights": np.asarray(weights, dtype=np.float32),
        },
    )


def save_and_get_sampler(training_client, name: str):
    """pytrio 0.2.3 的 save_weights_and_get_sampling_client() 不收 name，做个兼容。"""
    try:
        return training_client.save_weights_and_get_sampling_client(name=name)
    except TypeError:
        return training_client.save_weights_and_get_sampling_client()


def main() -> None:
    parser = argparse.ArgumentParser(description="PyTRIO 最小 SFT 示例")
    parser.add_argument("--base-model", default="Qwen/Qwen3.5-4B")
    parser.add_argument("--lora-rank", type=int, default=32, help="LoRA rank，范围 4-64")
    parser.add_argument("--iters", type=int, default=15, help="训练步数")
    parser.add_argument("--learning-rate", type=float, default=1e-4)
    parser.add_argument("--weights-name", default="what-is-trio", help="保存的权重名")
    args = parser.parse_args()

    service_client = trio.ServiceClient()
    training_client = service_client.create_lora_training_client(
        base_model=args.base_model,
        rank=args.lora_rank,
    )

    print("Loading tokenizer...")
    tokenizer = training_client.get_tokenizer()

    data = [build_sft_datum(ex, tokenizer) for ex in EXAMPLES]
    # 注意：传进 Datum 的 ndarray 会被包成 TensorData，读回来要 .to_numpy() / .tolist()
    all_weights = np.concatenate([d.loss_fn_inputs["weights"].to_numpy() for d in data])

    print(f"Start Training ({len(data)} 条样本 × {args.iters} 步)")
    for it in range(args.iters):
        # 两个 future 先都提交，再统一取结果 —— 云端可以连续排队，省一个来回
        fwd_future = training_client.forward_backward(data, "cross_entropy")
        opt_future = training_client.optim_step(
            trio.AdamParams(learning_rate=args.learning_rate)
        )
        fwd = fwd_future.result()
        opt_future.result()

        loss = fwd.metrics["loss:sum"] / all_weights.sum()
        print(f"Iter{it + 1:>3}  loss per token = {loss:.4f}")

    saved = training_client.save_weights_for_sampler(name=args.weights_name).result()
    print(f"\n权重已保存：{saved.path}")

    # 效果对比：评测一律用 temperature=0（贪心），否则看到的是采样噪声
    print("\nStart Sampling")
    base_client = service_client.create_sampling_client(base_model=args.base_model)
    sft_client = save_and_get_sampler(training_client, f"{args.weights_name}-eval")

    prompt = trio.ModelInput.from_ints(tokenizer.encode("Question: what is trio\nAnswer:"))
    params = trio.SamplingParams(max_tokens=24, temperature=0.0)

    base_out = base_client.sample(prompt=prompt, sampling_params=params, num_samples=1).result()
    sft_out = sft_client.sample(prompt=prompt, sampling_params=params, num_samples=1).result()

    print("Base:", repr(base_out.sequences[0].text))
    print("SFT :", repr(sft_out.sequences[0].text))


if __name__ == "__main__":
    main()
