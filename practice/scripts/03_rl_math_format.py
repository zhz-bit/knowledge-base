#!/usr/bin/env python3
"""RL 入门：用 importance_sampling 让模型只输出纯数字答案。

训练的是"格式服从"，不是算术能力 —— 基模本来就会算，但爱多说话。

循环：当前权重建 sampler → rollout → reward → advantage → Datum
      → forward_backward("importance_sampling") → optim_step

    trio login
    python 03_rl_math_format.py --iters 15
"""

import argparse
import re

import numpy as np
import pytrio as trio

TRAIN_SET = [
    ("What is 2 + 3?", 5), ("What is 7 - 4?", 3), ("What is 6 * 8?", 48),
    ("What is 12 / 3?", 4), ("Solve for x: x + 5 = 9", 4), ("Solve for x: 2x = 10", 5),
    ("What is 3 squared?", 9), ("What is the square root of 81?", 9),
    ("What is 15 + 27?", 42), ("What is 100 - 58?", 42),
]

EVAL_SET = [
    ("Solve for x: x + 7 = 12", 5), ("What is 9 * 7?", 63),
    ("What is 81 / 9?", 9), ("What is 14 + 28?", 42),
]

PROMPT_TMPL = "Question: {q}\nReturn only the final numeric answer.\nAnswer:"


def parse_number(text: str):
    """整段输出必须恰好是一个数字，多一个字都算格式错误。"""
    match = re.fullmatch(r"-?\d+(?:\.\d+)?", text.strip())
    return float(match.group()) if match else None


def compute_reward(text: str, gold: float) -> float:
    pred = parse_number(text)
    if pred is None:
        return -1.0                                     # 格式不对，重罚
    return 2.0 if abs(pred - gold) < 1e-6 else -0.5     # 对 / 错


def build_rl_datum(prompt_tokens, completion_tokens, completion_logprobs, advantage) -> trio.Datum:
    """prompt + completion → importance_sampling 用的 Datum。

    logprobs 传的是**采样那一刻**旧策略的 log q，来自 sequence.logprobs；
    新策略的 log p_theta 由服务器在 forward 时现算。方向别搞反。

    prompt 段没有采样 logprob，补 0；advantage 也补 0，等价于让 prompt 不参与损失。
    """
    tokens = prompt_tokens + completion_tokens

    old_logprobs = [0.0] * len(prompt_tokens) + [float(x or 0.0) for x in completion_logprobs]
    advantages = [0.0] * len(prompt_tokens) + [advantage] * len(completion_tokens)

    return trio.Datum(
        model_input=trio.ModelInput.from_ints(tokens=tokens[:-1]),
        loss_fn_inputs={
            "target_tokens": np.asarray(tokens[1:], dtype=np.int64),
            "logprobs": np.asarray(old_logprobs[1:], dtype=np.float32),
            "advantages": np.asarray(advantages[1:], dtype=np.float32),
        },
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="PyTRIO importance_sampling RL 示例")
    parser.add_argument("--base-model", default="Qwen/Qwen3.5-4B")
    parser.add_argument("--lora-rank", type=int, default=32)
    parser.add_argument("--iters", type=int, default=15, help="RL 步数")
    parser.add_argument("--group-size", type=int, default=4, help="每题采样几条")
    parser.add_argument("--max-tokens", type=int, default=8)
    parser.add_argument("--temperature", type=float, default=0.7, help="rollout 温度")
    parser.add_argument("--learning-rate", type=float, default=1e-5)
    parser.add_argument("--loss-fn", default="importance_sampling",
                        choices=["importance_sampling", "ppo"],
                        help="ppo 的输入字段完全相同，只是内部多一步 clip")
    args = parser.parse_args()

    service_client = trio.ServiceClient()
    training_client = service_client.create_lora_training_client(
        base_model=args.base_model, rank=args.lora_rank
    )
    print("Loading tokenizer...")
    tokenizer = training_client.get_tokenizer()

    print("Start RL Training")
    for it in range(args.iters):
        # 每步都用当前最新权重重建 sampler —— 这是"on-policy"的关键
        sampler = training_client.save_weights_and_get_sampling_client()

        batch, rewards, correct, total = [], [], 0, 0
        for question, gold in TRAIN_SET:
            prompt_tokens = tokenizer.encode(
                PROMPT_TMPL.format(q=question), add_special_tokens=True
            )
            result = sampler.sample(
                prompt=trio.ModelInput.from_ints(prompt_tokens),
                sampling_params=trio.SamplingParams(
                    max_tokens=args.max_tokens, temperature=args.temperature
                ),
                num_samples=args.group_size,
            ).result()

            for seq in result.sequences:
                reward = compute_reward(seq.text, float(gold))
                pred = parse_number(seq.text)
                rewards.append(reward)
                total += 1
                correct += int(pred is not None and abs(pred - gold) < 1e-6)

                if seq.tokens:
                    batch.append(
                        build_rl_datum(prompt_tokens, list(seq.tokens), list(seq.logprobs), reward)
                    )

        fwd_future = training_client.forward_backward(batch, args.loss_fn)
        opt_future = training_client.optim_step(
            trio.AdamParams(learning_rate=args.learning_rate)
        )
        fwd_future.result()
        opt_future.result()

        print(f"Iter{it + 1:>3} | reward={np.mean(rewards):+.4f} | "
              f"acc={correct / max(total, 1):.4f} | rollouts={len(batch)}")

    # 评估：贪心解码，看格式是否变干净
    print("\nStart Evaluation")
    base_client = service_client.create_sampling_client(base_model=args.base_model)
    rl_client = training_client.save_weights_and_get_sampling_client()
    greedy = trio.SamplingParams(max_tokens=args.max_tokens, temperature=0.0)

    for question, gold in EVAL_SET:
        prompt = trio.ModelInput.from_ints(
            tokenizer.encode(PROMPT_TMPL.format(q=question), add_special_tokens=True)
        )
        base_text = base_client.sample(
            prompt=prompt, sampling_params=greedy, num_samples=1
        ).result().sequences[0].text.strip()
        rl_text = rl_client.sample(
            prompt=prompt, sampling_params=greedy, num_samples=1
        ).result().sequences[0].text.strip()

        print("=" * 62)
        print(f"Q: {question} | Gold: {gold}")
        print(f"  Base: {base_text!r:<34} -> {parse_number(base_text)}")
        print(f"  RL  : {rl_text!r:<34} -> {parse_number(rl_text)}")


if __name__ == "__main__":
    main()
