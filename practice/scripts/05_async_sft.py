#!/usr/bin/env python3
"""异步 SFT：把"等云端"的时间用来干本地的活。

异步调用分两阶段：

    fut = await client.forward_backward_async(...)   # ① 提交，立刻返回
    # ... 本地继续：准备下一批数据、算指标、写日志
    res = await fut                                  # ② 显式等待

对照 02_sft_what_is_trio.py 看差异：训练步连续提交，loss 的计算与打印挂起，
最后 asyncio.gather 一次收完。

    trio login
    python 05_async_sft.py --iters 15
"""

import argparse
import asyncio

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
    prompt = f"Question: {example['input']}\nAnswer:"

    prompt_tokens = tokenizer.encode(prompt, add_special_tokens=True)
    prompt_weights = [0] * len(prompt_tokens)
    completion_tokens = tokenizer.encode(f" {example['output']}\n\n", add_special_tokens=False)
    completion_weights = [1] * len(completion_tokens)

    tokens = prompt_tokens + completion_tokens
    weights = prompt_weights + completion_weights

    return trio.Datum(
        model_input=trio.ModelInput.from_ints(tokens=tokens[:-1]),
        loss_fn_inputs={
            "target_tokens": np.asarray(tokens[1:], dtype=np.int32),
            "weights": np.asarray(weights[1:], dtype=np.float32),
        },
    )


async def main() -> None:
    parser = argparse.ArgumentParser(description="PyTRIO 异步 SFT 示例")
    parser.add_argument("--base-model", default="Qwen/Qwen3.5-4B")
    parser.add_argument("--lora-rank", type=int, default=32)
    parser.add_argument("--iters", type=int, default=15)
    parser.add_argument("--learning-rate", type=float, default=1e-4)
    args = parser.parse_args()

    service_client = trio.ServiceClient()
    training_client = await service_client.create_lora_training_client_async(
        base_model=args.base_model, rank=args.lora_rank
    )

    print("Loading tokenizer...")
    tokenizer = training_client.get_tokenizer()   # 本地操作，无异步版本

    data = [build_sft_datum(ex, tokenizer) for ex in EXAMPLES]
    # 注意：传进 Datum 的 ndarray 会被包成 TensorData，读回来要 .to_numpy() / .tolist()
    all_weights = np.concatenate([d.loss_fn_inputs["weights"].to_numpy() for d in data])

    async def report(fwd_future, opt_future, it: int) -> float:
        fwd = await fwd_future
        await opt_future
        logprobs = np.concatenate([o["logprobs"].to_numpy() for o in fwd.loss_fn_outputs])
        loss = -np.dot(logprobs, all_weights) / all_weights.sum()
        print(f"Iter{it + 1:>3} loss per token = {loss:.4f}")
        return float(loss)

    print("Start Training")
    pending = []
    for it in range(args.iters):
        fwd_future = await training_client.forward_backward_async(data, "cross_entropy")
        opt_future = await training_client.optim_step_async(
            trio.AdamParams(learning_rate=args.learning_rate)
        )
        # 不在这里 await 结果 —— 挂进队列，循环立刻提交下一步
        pending.append(report(fwd_future, opt_future, it))

    await asyncio.gather(*pending)

    print("\nStart Sampling")
    base_client = await service_client.create_sampling_client_async(base_model=args.base_model)
    try:
        sft_client = await training_client.save_weights_and_get_sampling_client_async(
            name="what-is-trio-async"
        )
    except TypeError:                              # pytrio 0.2.3 无 name 参数
        sft_client = await training_client.save_weights_and_get_sampling_client_async()

    prompt = trio.ModelInput.from_ints(tokenizer.encode("Question: what is trio\nAnswer:"))
    params = trio.SamplingParams(max_tokens=24, temperature=0.0)

    # 两次采样也可以并发提交
    base_future = await base_client.sample_async(prompt=prompt, sampling_params=params, num_samples=1)
    sft_future = await sft_client.sample_async(prompt=prompt, sampling_params=params, num_samples=1)
    base_out = await base_future
    sft_out = await sft_future

    print("Base:", repr(base_out.sequences[0].text))
    print("SFT :", repr(sft_out.sequences[0].text))


if __name__ == "__main__":
    asyncio.run(main())
