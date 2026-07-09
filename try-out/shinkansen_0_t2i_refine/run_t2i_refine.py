"""
0系新幹線 s方向レンダーのcanny edgeを弱ControlNet(strength 0.3〜0.4)で誘導し、
「あるべき0系」の目標画像を複数シードで生成するランナー。

try-out/t2i_research/comfyui_api_test.py の run_workflow() 等を再利用する。

Usage:
    python run_t2i_refine.py [--round N]
"""
from __future__ import annotations

import argparse
import copy
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
RESEARCH_DIR = SCRIPT_DIR.parent / "t2i_research"
sys.path.insert(0, str(RESEARCH_DIR))

from comfyui_api_test import (  # noqa: E402
    check_server_alive,
    load_workflow,
    run_workflow,
)

WORKFLOW_PATH = SCRIPT_DIR / "sdxl_controlnet_canny_api.json"
OUTPUT_DIR = SCRIPT_DIR / "output"

SEEDS = [42, 123, 777]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--round", type=int, default=1, help="ラウンド番号(ファイル名prefixに使う)")
    parser.add_argument("--strength", type=float, default=None, help="workflow中のstrengthを上書き")
    parser.add_argument(
        "--workflow", type=Path, default=WORKFLOW_PATH,
        help="使用するworkflow JSON（既定はsdxl_controlnet_canny_api.json、"
             "側面図実験ではsdxl_controlnet_canny_side_api.json等を指定する）",
    )
    parser.add_argument(
        "--prefix", default="shinkansen0_t2i",
        help="filename_prefixの接頭辞（既定'shinkansen0_t2i'、側面図実験では'shinkansen0_side_t2i'等）",
    )
    args = parser.parse_args()

    print("[main] ComfyUI疎通確認")
    if not check_server_alive():
        raise SystemExit("ComfyUIサーバーに接続できません。先に起動してください。")
    print("[main] サーバー疎通OK")

    base_workflow = load_workflow(args.workflow)
    if args.strength is not None:
        base_workflow["11"]["inputs"]["strength"] = args.strength
        print(f"[main] strength override: {args.strength}")

    for seed in SEEDS:
        workflow = copy.deepcopy(base_workflow)
        workflow["3"]["inputs"]["seed"] = seed
        workflow["9"]["inputs"]["filename_prefix"] = f"{args.prefix}_r{args.round}_seed{seed}"

        print(f"\n[main] === round={args.round} seed={seed} ===")
        paths = run_workflow(workflow, output_dir=OUTPUT_DIR, timeout=300.0)
        for path in paths:
            print(f"  -> {path}")


if __name__ == "__main__":
    main()
