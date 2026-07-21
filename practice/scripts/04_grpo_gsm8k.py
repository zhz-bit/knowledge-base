#!/usr/bin/env python3
"""GRPO on GSM8K：同一道题采一组回答，用组内 reward 均值做基线。

和 03 的唯一区别是 advantage 的算法：

    A_i = r_i - mean(r_1..r_G)

组内相对优势不需要单独训 value model，这是 GRPO 比 PPO 轻的地方。
损失函数仍然是 importance_sampling。

    trio login
    pip install datasets tqdm
    python 04_grpo_gsm8k.py --steps 20 --batch-size 4 --group-size 4 --max-tokens 512

数据集首次运行会由 datasets 自动下载缓存（openai/gsm8k, main/train）。
"""

import argparse
import re
from dataclasses import dataclass

import numpy as np
import pytrio as trio
from datasets import Dataset, load_dataset
from tqdm import tqdm

QUESTION_SUFFIX = " Provide a numerical answer without units, written inside \\boxed{}."

# 一条 few-shot 示范，让模型知道答案要放进 \boxed{}
FEWSHOT_PREFIX = [
    {"role": "user", "content": "How many r's are in strawberry?" + QUESTION_SUFFIX},
    {"role": "assistant", "content": (
        "<think>\n\n</think>\n\n"
        "Let's spell the word out and number all the letters: "
        "1) s 2) t 3) r 4) a 5) w 6) b 7) e 8) r 9) r 10) y. "
        "We have r's at positions 3, 8, and 9. There are three r's. \\boxed{3}"
    )},
]


@dataclass
class Rollout:
    tokens: list[int]
    logprobs: list[float]
    text: str
    reward: float
    advantage: float


# ── reward：纯规则判分 ────────────────────────────────────────────────
def extract_boxed(text: str) -> str | None:
    matches = re.findall(r"\\boxed\{([^}]+)\}", text)
    return matches[-1].strip() if matches else None


def normalize_answer(text: str) -> str:
    return text.replace(",", "").strip().rstrip(".")


def grade_answer(response: str, ground_truth: str) -> float:
    answer = extract_boxed(response)
    if answer is None:
        return 0.0
    return 1.0 if normalize_answer(answer) == normalize_answer(ground_truth) else 0.0


def extract_gsm8k_answer(answer_text: str) -> str:
    """GSM8K 的标准答案在 `####` 之后。"""
    match = re.search(r"####\s*(.+)", answer_text)
    if match is None:
        raise ValueError(f"No GSM8K final answer found: {answer_text!r}")
    return normalize_answer(match.group(1))


# ── prompt / rollout / Datum ─────────────────────────────────────────
def build_prompt(tokenizer, question: str) -> list[int]:
    messages = [*FEWSHOT_PREFIX, {"role": "user", "content": question + QUESTION_SUFFIX}]
    prompt_text = tokenizer.apply_chat_template(
        messages, tokenize=False, add_generation_prompt=True, enable_thinking=False
    )
    prompt_tokens = tokenizer.encode(prompt_text, add_special_tokens=False)
    if not prompt_tokens:
        raise ValueError("Prompt tokens are empty")
    return prompt_tokens


def run_rollout_group(sampler, tokenizer, prompt_tokens, ground_truth,
                      sampling_params, group_size) -> list[Rollout]:
    """对同一个 prompt 采 group_size 条，算完整组 reward 后再减均值。"""
    result = sampler.sample(
        prompt=trio.ModelInput.from_ints(prompt_tokens),
        num_samples=group_size,
        sampling_params=sampling_params,
        return_text=True,
    ).result()

    raw, rewards = [], []
    for seq in result.sequences:
        text = seq.text
        if text is None:
            text = tokenizer.decode(seq.tokens, skip_special_tokens=True)

        tokens = list(seq.tokens)
        logprobs = [float(v) for v in seq.logprobs]
        if len(tokens) != len(logprobs):
            raise ValueError(f"token/logprob 长度不一致：{len(tokens)} != {len(logprobs)}")

        reward = grade_answer(text, ground_truth)
        rewards.append(reward)
        raw.append((tokens, logprobs, text))

    mean_reward = sum(rewards) / len(rewards)
    return [
        Rollout(tokens=t, logprobs=lp, text=tx, reward=r, advantage=r - mean_reward)
        for (t, lp, tx), r in zip(raw, rewards, strict=True)
    ]


def build_grpo_datum(prompt_tokens: list[int], sample: Rollout) -> trio.Datum:
    """自回归对齐：

        input  = prompt + completion[:-1]
        target = [0]*(len(prompt)-1) + completion

    前 len(prompt)-1 个位置属于 prompt 内部预测，不训练，用 0 / 0.0 占位；
    从最后一个 prompt token 开始才预测 completion。
    """
    if not sample.tokens:
        raise ValueError("Cannot train on an empty completion")

    observation_len = len(prompt_tokens) - 1
    input_tokens = prompt_tokens + sample.tokens[:-1]
    target_tokens = [0] * observation_len + sample.tokens
    padded_logprobs = [0.0] * observation_len + sample.logprobs
    padded_advantages = [0.0] * observation_len + [sample.advantage] * len(sample.tokens)

    lengths = {len(input_tokens), len(target_tokens), len(padded_logprobs), len(padded_advantages)}
    if len(lengths) != 1:
        raise ValueError(f"GRPO datum 各字段长度必须一致，实际 {lengths}")

    return trio.Datum(
        model_input=trio.ModelInput.from_ints(input_tokens),
        loss_fn_inputs={
            "target_tokens": np.asarray(target_tokens, dtype=np.int64),
            "logprobs": np.asarray(padded_logprobs, dtype=np.float32),
            "advantages": np.asarray(padded_advantages, dtype=np.float32),
        },
    )


def pick_batch(dataset: Dataset, step: int, batch_size: int) -> Dataset:
    start = step * batch_size
    return dataset.select([(start + i) % len(dataset) for i in range(batch_size)])


def get_stop_sequences(tokenizer) -> list[str]:
    candidates = [tokenizer.eos_token, "<|im_end|>"]
    return list(dict.fromkeys([t for t in candidates if t]))


def main() -> None:
    parser = argparse.ArgumentParser(description="PyTRIO GRPO / GSM8K demo")
    parser.add_argument("--base-model", default="Qwen/Qwen3.5-4B")
    parser.add_argument("--lora-rank", type=int, default=32)
    parser.add_argument("--steps", type=int, default=20, help="优化步数")
    parser.add_argument("--batch-size", type=int, default=4, help="每步几道题")
    parser.add_argument("--group-size", type=int, default=4, help="每题采样几条")
    parser.add_argument("--max-tokens", type=int, default=512)
    parser.add_argument("--temperature", type=float, default=1.0)
    parser.add_argument("--top-p", type=float, default=1.0)
    parser.add_argument("--learning-rate", type=float, default=4e-5)
    parser.add_argument("--skip-degenerate", action="store_true",
                        help="跳过整组全对/全错的题（advantage 全 0，对梯度无贡献）")
    parser.add_argument("--weights-name", default="grpo-gsm8k")
    args = parser.parse_args()

    dataset = load_dataset("openai/gsm8k", "main", split="train")
    print(f"GSM8K train: {len(dataset)} 条")

    service_client = trio.ServiceClient()
    training_client = service_client.create_lora_training_client(
        base_model=args.base_model, rank=args.lora_rank
    )
    print("Loading tokenizer...")
    tokenizer = training_client.get_tokenizer()

    sampling_params = trio.SamplingParams(
        max_tokens=args.max_tokens,
        temperature=args.temperature,
        top_p=args.top_p,
        stop=get_stop_sequences(tokenizer),
    )

    print("Start GRPO Training")
    for step in range(args.steps):
        sampler = training_client.save_weights_and_get_sampling_client()
        batch = pick_batch(dataset, step, args.batch_size)

        data, all_rewards, skipped = [], [], 0
        for row in tqdm(batch, desc=f"step {step + 1}/{args.steps} rollout", leave=False):
            prompt_tokens = build_prompt(tokenizer, row["question"])
            ground_truth = extract_gsm8k_answer(row["answer"])

            group = run_rollout_group(
                sampler, tokenizer, prompt_tokens, ground_truth,
                sampling_params, args.group_size,
            )
            all_rewards.extend(s.reward for s in group)

            # 整组 advantage 全 0 时这组数据没有梯度贡献
            if args.skip_degenerate and all(abs(s.advantage) < 1e-9 for s in group):
                skipped += 1
                continue

            data.extend(build_grpo_datum(prompt_tokens, s) for s in group if s.tokens)

        if not data:
            print(f"Step{step + 1:>3} | 本步全部样本被跳过，无梯度可更新")
            continue

        fwd_future = training_client.forward_backward(data, "importance_sampling")
        opt_future = training_client.optim_step(
            trio.AdamParams(learning_rate=args.learning_rate)
        )
        fwd_future.result()
        opt_future.result()

        note = f" | skipped_groups={skipped}" if args.skip_degenerate else ""
        print(f"Step{step + 1:>3} | acc={np.mean(all_rewards):.4f} | "
              f"rollouts={len(data)}{note}")

    saved = training_client.save_weights_for_sampler(name=args.weights_name).result()
    print(f"\n权重已保存：{saved.path}")


if __name__ == "__main__":
    main()
