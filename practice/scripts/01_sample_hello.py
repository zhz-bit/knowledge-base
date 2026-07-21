#!/usr/bin/env python3
"""最小推理：连接 TRIO，用基模生成一段文本。

先跑通这个，再看别的脚本。

    trio login
    python 01_sample_hello.py
    python 01_sample_hello.py --prompt "用一句话解释 LoRA" --num-samples 4
"""

import argparse

import pytrio as trio


def main() -> None:
    parser = argparse.ArgumentParser(description="PyTRIO 最小推理示例")
    parser.add_argument("--base-model", default="Qwen/Qwen3.5-4B", help="基础模型名")
    parser.add_argument("--prompt", default="用一句话解释什么是 LoRA。", help="用户输入")
    parser.add_argument("--num-samples", type=int, default=1, help="一次生成几条")
    parser.add_argument("--max-tokens", type=int, default=128, help="最多生成 token 数")
    parser.add_argument("--temperature", type=float, default=0.7, help="采样温度，0 = 贪心")
    parser.add_argument("--seed", type=int, default=42, help="随机种子")
    parser.add_argument("--show-logprobs", action="store_true", help="逐 token 打印 logprob")
    args = parser.parse_args()

    # 1. 与 TRIO 建立连接
    service_client = trio.ServiceClient()
    print("可用模型：", service_client.get_supported_models())

    # 2. 创建推理客户端
    sampling_client = service_client.create_sampling_client(base_model=args.base_model)

    # 3. 拿 tokenizer，把文本转成 token id（TRIO 的输入是 token，不是字符串）
    print("Loading tokenizer...")
    tokenizer = sampling_client.get_tokenizer()
    messages = [{"role": "user", "content": args.prompt}]
    prompt_text = tokenizer.apply_chat_template(
        messages, tokenize=False, add_generation_prompt=True
    )
    prompt_ids = tokenizer.encode(prompt_text, add_special_tokens=False)
    print(f"prompt: {len(prompt_ids)} tokens")

    # 4. 采样。同步方法返回 future，.result() 才阻塞等待
    response = sampling_client.sample(
        prompt=trio.ModelInput.from_ints(prompt_ids),
        num_samples=args.num_samples,
        sampling_params=trio.SamplingParams(
            max_tokens=args.max_tokens,
            temperature=args.temperature,
            seed=args.seed,
        ),
    ).result()

    for i, seq in enumerate(response.sequences):
        print(f"\n--- sample {i} (stop_reason={seq.stop_reason}) ---")
        print(seq.text)
        if args.show_logprobs:
            print("  token 级 logprobs：")
            for token_id, logprob in zip(seq.tokens, seq.logprobs):
                print(f"    {tokenizer.decode([token_id])!r:<16} {logprob}")

    print(f"\n本次共生成 {response.output_tokens} 个 token")


if __name__ == "__main__":
    main()
