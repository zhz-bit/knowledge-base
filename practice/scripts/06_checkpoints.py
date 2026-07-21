#!/usr/bin/env python3
"""Checkpoint 管理：列出 / 下载 / 查看训练记录。

    trio login
    python 06_checkpoints.py --list
    python 06_checkpoints.py --download <CHECKPOINT_ID>
    python 06_checkpoints.py --runs

下载得到的是 zip 包，解压后是 PEFT 格式的 LoRA adapter（不是完整模型）：

    checkpoint/
    ├── adapter_config.json         # rank / alpha / 目标层
    ├── adapter_model.safetensors   # adapter 权重
    └── generation_config.json

部署时必须配上对应的 base model，见本目录 README 的「本地部署」一节。
"""

import argparse
from pathlib import Path

import pytrio as trio


def main() -> None:
    parser = argparse.ArgumentParser(description="PyTRIO checkpoint 管理")
    parser.add_argument("--list", action="store_true", help="列出账号下的权重")
    parser.add_argument("--runs", action="store_true", help="列出训练运行记录")
    parser.add_argument("--download", metavar="CHECKPOINT_ID", help="下载指定权重")
    parser.add_argument("--out-dir", default=".", help="下载目录")
    parser.add_argument("--limit", type=int, default=50)
    args = parser.parse_args()

    if not (args.list or args.runs or args.download):
        parser.error("至少指定 --list / --runs / --download 之一")

    service_client = trio.ServiceClient()
    rest_client = service_client.create_rest_client()

    if args.list:
        print("== 权重列表 ==")
        print(rest_client.list_user_checkpoints(limit=args.limit).result())

    if args.runs:
        print("== 训练运行 ==")
        print(rest_client.list_training_runs(limit=args.limit).result())

    if args.download:
        out_path = Path(args.out_dir) / f"{args.download}.zip"
        out_path.parent.mkdir(parents=True, exist_ok=True)

        # download_checkpoint 是 0.2.3 提供的封装（支持断点续传）
        result = rest_client.download_checkpoint(
            args.download, destination_path=str(out_path)
        ).result()
        print(f"下载完成：{out_path.resolve()}")
        print(result)

        # 手动版（官方文档写法，效果相同）：
        #   url = rest_client.get_checkpoint_archive_url(args.download).result().url
        #   with requests.get(url, stream=True) as r:
        #       r.raise_for_status()
        #       with open(out_path, "wb") as f:
        #           for chunk in r.iter_content(chunk_size=8192):
        #               f.write(chunk)


if __name__ == "__main__":
    main()
