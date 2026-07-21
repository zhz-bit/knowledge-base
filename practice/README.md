# PyTRIO 实践

把 [docs.pytrio.com](https://docs.pytrio.com/docs) 的示例整理成一条能从头跑到尾的路径。

**TRIO 是什么**：LLM 后训练（post-training）的云端计算引擎。你在自己的 CPU 机器上写脚本 ——
数据、损失函数、训练循环全部由你掌控 —— 分布式训练的脏活交给云端。换模型只改一个字符串。
目前提供 LoRA 微调（非全量），支持 SFT 与 RL 两种范式。

四个动词就是全部：`forward_backward`（算梯度）、`optim_step`（更新权重）、
`sample`（生成 + 返回 logprobs）、`save_weights_*`（存权重 / 存权重+优化器）。

---

## 目录

```
practice/
├── pytrio-quickstart.ipynb   ← 主线：13 章，逐段解释 + 可执行
├── requirements.txt
└── scripts/                  ← 可直接跑的完整脚本（适合长训练）
    ├── 01_sample_hello.py        最小推理
    ├── 02_sft_what_is_trio.py    最小 SFT
    ├── 03_rl_math_format.py      RL：importance_sampling
    ├── 04_grpo_gsm8k.py          GRPO on GSM8K
    ├── 05_async_sft.py           异步 SFT
    └── 06_checkpoints.py         权重列出 / 下载
```

**建议路径**：先在 notebook 里从头读到 §6（推理 → Datum → 第一次 SFT），
搞懂 `Datum` 的对齐规则后，再挑 §7 之后感兴趣的章节；要跑真训练时切到 `scripts/`。

---

## 环境准备

`pytrio` 要求 **Python ≥ 3.10**（macOS 自带的 3.9 装不上；Colab 是 3.12，没问题）。

### 在 Colab 上跑（含 VS Code 连 Colab 运行时）

**什么都不用先准备** —— 打开 `pytrio-quickstart.ipynb`，§0 的三格会自己装包、自检、登录。
只需要手上有一个 API Key（[pytrio.cn/dashboard](https://pytrio.cn/dashboard) 复制）。

几件值得先知道的事：

- **不用选 GPU 运行时**。训练和推理全在 TRIO 自己的云端 GPU 上跑，
  这个 notebook 只负责组数据、发请求、收结果，CPU 运行时完全够用。
- **每次新建运行时都要重跑 §0 的三格**。Colab 的磁盘和已装的包在会话结束后会清空，
  `~/.pytrio/config.toml` 里的登录凭证也一起没了。
- **装完可能要重启内核**。`pip install pytrio` 会升级 Colab 预装的 `transformers` / `pydantic`，
  §0 的自检格（②）会明确告诉你要不要重启。
- **建议把 key 存进 Colab Secrets**：左侧边栏 🔑「密钥」面板，命名 `TRIO_API_KEY`，
  打开本 notebook 的访问开关。之后每个会话自动读取，不用手输。
  读不到会自动退回手动输入（不回显，key 不会留在 notebook 里）。
- **`scripts/` 不在 Colab 上**。notebook 是自包含的，不依赖它们；
  想在 Colab 跑脚本就把内容贴进 cell，或先 `!git clone` 这个仓库。
- **会话会断，但权重在云端不会丢**。免费版闲置约 90 分钟、单次最长 12 小时就断连。
  应对办法不是"别断"，而是在训练循环里定期 `save_state()` ——
  权重存在 TRIO 服务端而不是 Colab 磁盘上，重连后重跑 §0 三格，
  用 `create_training_client_from_state_with_optimizer(path=...)` 从断点续上就行（§11）。
- **下载的权重也会随会话消失**。§11 的下载格有个 `SAVE_TO_DRIVE` 开关，
  打开就落到 Google Drive；或者用 `files.download()` 拉回本机。

### 在本地跑

```bash
cd practice

uv venv --python 3.12 .venv && source .venv/bin/activate
uv pip install -r requirements.txt
# 或：python3.12 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt

trio login          # 终端交互，粘贴 API Key 时不回显是正常的
```

登录信息存在 `~/.pytrio/config.toml`，只需一次。启动 notebook：

```bash
python -m ipykernel install --user --name pytrio --display-name "Python (pytrio)"
jupyter lab pytrio-quickstart.ipynb
```

国内网络慢时加镜像：`-i https://mirrors.cernet.edu.cn/pypi/web/simple`

> 本地环境下 §0 的安装格是幂等的，重跑无害；登录格也可以直接跑，
> 效果和在终端敲 `trio login` 一样。

---

## 花额度提醒

训练和采样都真实消耗账号 token 额度。**不要对 notebook 直接 Run All**。
notebook 里带 💸 的 cell 会调用云端，带 ❌ 的纯本地不花钱（§4 Datum、§8 advantage 演示）。

各章节默认步数都调小了（SFT 12 步、RL 3 步），够看流程但看不出效果提升；
想看到真实收敛请用 `scripts/` 里的脚本调大 `--iters` / `--steps`。

---

## 三分钟版本

```python
import numpy as np, pytrio as trio

sc = trio.ServiceClient()
tc = sc.create_lora_training_client(base_model="Qwen/Qwen3.5-4B", rank=32)
tok = tc.get_tokenizer()

# 1) 组 Datum：prompt 段 weights=0，自回归右移一位
p = tok.encode("Question: what is trio\nAnswer:", add_special_tokens=True)
c = tok.encode(" trio is an AI Infra product.\n\n", add_special_tokens=False)
tokens, weights = p + c, [0] * len(p) + [1] * len(c)
datum = trio.Datum(
    model_input=trio.ModelInput.from_ints(tokens[:-1]),
    loss_fn_inputs={"target_tokens": np.asarray(tokens[1:], np.int32),
                    "weights":       np.asarray(weights[1:], np.float32)},
)

# 2) 训练：两个 future 先都提交，再统一取结果
for _ in range(15):
    fwd = tc.forward_backward([datum], "cross_entropy")
    opt = tc.optim_step(trio.AdamParams(learning_rate=1e-4))
    print(fwd.result().metrics["loss:sum"]); opt.result()

# 3) 存权重并当场验证
sampler = tc.save_weights_and_get_sampling_client()
print(sampler.sample(
    prompt=trio.ModelInput.from_ints(p),
    sampling_params=trio.SamplingParams(max_tokens=24, temperature=0.0),
).result().sequences[0].text)
```

---

## 最容易踩的几个坑

1. **Python 必须 ≥ 3.10**。
2. **Colab 每个新会话都要重跑 §0 的三格**：装的包和登录凭证都随运行时清空。
   `pip install pytrio` 会升级 Colab 预装的 `transformers` / `pydantic`，装完常需重启内核。
3. **notebook 里把 key 显式传给 `ServiceClient`，别指望配置文件**。
   `ServiceClient` 只在 `sys.stdin.isatty()` 为真时才弹 API Key 输入提示，
   Jupyter / Colab 内核的 stdin 不是 TTY —— 提示被静默跳过，然后直接抛
   `AuthError: API key is required (code=auth.missing_api_key)`。
   `trio login --api-key` 落盘到 `~/.pytrio/config.toml` 这条路在 Colab 上**不总是生效**，
   而且失败时不中断 cell，很容易被忽略然后在下一格才炸。
   实测最可靠的是 `trio.ServiceClient(api_key=KEY)` —— 无配置文件也能通，
   §0 ③ 就是这么做的，并且会当场建一次 client 来验证。
4. **能连上不等于能跑**。登录、`get_supported_models()`、`create_rest_client()` 都免费，
   余额为 0 也照样成功；第一个撞 `billing_insufficient_balance`(409) 的是
   `create_sampling_client()` —— 建 sampling / training 会话就开始计费。
   别把"登录成功"当成环境已就绪。
5. **Colab 会话会断，但权重在云端不会丢**。定期 `save_state()`，重连后用
   `create_training_client_from_state_with_optimizer(path=...)` 续训。
   下载的权重文件同样随会话消失 —— 存 Google Drive 或 `files.download()` 拉回本机。
6. **别忘了右移一位**：`input=tokens[:-1]`、`target=tokens[1:]`、`weights=weights[1:]`。
   `loss_fn_inputs` 里每个数组的长度都必须等于 `model_input` 的长度。
7. **prompt 的 `weights` 要置 0**，否则模型连你的问题一起背。
   RL 里对应把 prompt 段的 `advantages` 置 0。
8. **`logprobs` 传的是"采样那一刻"的**（来自 `sequence.logprobs`，即 log q），
   不是当前策略的。当前策略的 log p_θ 由服务器 forward 时现算。传反了 loss 就没意义。
9. **评测用 `temperature=0.0`**，rollout 用 `0.7~1.0`。混着用会把噪声当成效果。
10. **两个 future 先都提交再 `.result()`**，否则白等一个来回。
11. **`loss_fn_inputs` 读回来是 `TensorData` 不是 numpy**。传进去时是 `np.ndarray`，
    但 pydantic 会包一层，取回要 `d.loss_fn_inputs["weights"].to_numpy()`（或 `.tolist()`）。
    直接 `np.concatenate([...])` 会报 *zero-dimensional arrays cannot be concatenated*。
    `forward_backward` 返回的 `loss_fn_outputs[i]["logprobs"]` 同理。
12. **GRPO 里整组全对/全错没有梯度贡献**（advantage 全 0），可以过滤掉省额度
    （`04_grpo_gsm8k.py --skip-degenerate`）。
13. **官方文档比 PyPI 版本新**。`pytrio 0.2.3` 的
    `save_weights_and_get_sampling_client()` 不接受 `name`，
    `create_lora_training_client` 也没有 `lora_path` / `trainable_token_indices`。
    写代码前 `inspect.signature(...)` 查一下已装版本的真实签名。
14. **`forward_backward_custom` 贵**：多一次 forward，FLOPs ≈ 1.5×，实测耗时最多 3×。
    能用内置损失（`cross_entropy` / `importance_sampling` / `ppo`）就别自定义。

---

## 本地部署训练结果

下载的 zip 解压后是 **LoRA adapter**（PEFT 格式），不是完整模型，必须配 base model：

```bash
pip install modelscope
python -c "from modelscope import snapshot_download; snapshot_download('Qwen/Qwen3.5-4B', local_dir='./base_model')"
```

**方式一：Transformers + PEFT**（不合并，验证最快）

```python
model = AutoModelForCausalLM.from_pretrained("./base_model", dtype=torch.bfloat16, device_map="auto")
model = PeftModel.from_pretrained(model, "./checkpoint")
```

**方式二：合并成独立模型**（之后可用 vLLM / SGLang / Ollama）

```python
model = PeftModel.from_pretrained(base, "./checkpoint").merge_and_unload()
model.save_pretrained("./merged_model", safe_serialization=True)
```

---

## 参考

- 官方文档：<https://docs.pytrio.com/docs>（`llms-full.txt` 是全文纯文本版，喂给 Agent 很方便）
- 官方案例：Chat-甄嬛（SFT）、GSM8K（RL）、GRPO、On-Policy Distillation（蒸馏）、DPO
- 模型与计费：<https://pytrio.cn/home/pricing>
- PyTRIO Skill（让 Claude Code / Codex 先读官方文档再写代码，避免误套 PyTorch/HF 写法）：
  `npx skills add SwanHubX/pytrio-skill -g -y`
