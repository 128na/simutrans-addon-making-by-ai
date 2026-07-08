"""建物周辺装飾inpaintワークフローを実行する。

try-out/t2i_research/comfyui_api_test.py の run_workflow() 等を再利用し、
inpaint_controlnet_api.json (SDXL inpainting + ControlNet canny) を
複数seedで実行して output/ に保存する。

事前に prepare_canvas.py を実行し、生成した canvas.png / mask.png / silhouette.png を
E:\\ComfyUI\\input\\ に t2ipoc_canvas.png / t2ipoc_mask.png / t2ipoc_silhouette.png として
コピーしておくこと(LoadImage/LoadImageMaskノードはComfyUIのinputディレクトリを参照する)。

使い方:
    python run_inpaint.py --seeds 42 123 777
"""

from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR.parent / "t2i_research"))

from comfyui_api_test import check_server_alive, load_workflow, run_workflow  # noqa: E402

DEFAULT_WORKFLOW_PATH = SCRIPT_DIR / "inpaint_controlnet_api.json"
OUTPUT_DIR = SCRIPT_DIR / "output"


def main() -> None:
    parser = argparse.ArgumentParser(description="建物周辺装飾inpaintワークフロー実行")
    parser.add_argument("--seeds", type=int, nargs="+", default=[42])
    parser.add_argument("--controlnet-strength", type=float, default=0.6)
    parser.add_argument("--steps", type=int, default=25)
    parser.add_argument("--cfg", type=float, default=7.0)
    parser.add_argument("--prompt", type=str, default=None, help="positive promptを上書き(未指定ならworkflow JSON内のデフォルトを使用)")
    parser.add_argument("--negative", type=str, default=None, help="negative promptを上書き")
    parser.add_argument("--prefix", type=str, default="t2ipoc_inpaint", help="出力ファイル名prefix")
    parser.add_argument("--workflow", type=Path, default=DEFAULT_WORKFLOW_PATH)
    args = parser.parse_args()

    print("[run_inpaint] ComfyUI疎通確認...")
    if not check_server_alive():
        raise SystemExit(
            "ComfyUIサーバーに接続できません。\n"
            r"E:\ComfyUI\venv\Scripts\python.exe E:\ComfyUI\main.py を起動してから再実行してください。"
        )
    print("[run_inpaint] サーバー疎通OK")

    base_workflow = load_workflow(args.workflow)

    all_paths = []
    for seed in args.seeds:
        workflow = copy.deepcopy(base_workflow)
        workflow["11"]["inputs"]["seed"] = seed
        workflow["11"]["inputs"]["steps"] = args.steps
        workflow["11"]["inputs"]["cfg"] = args.cfg
        workflow["9"]["inputs"]["strength"] = args.controlnet_strength
        if args.prompt is not None:
            workflow["2"]["inputs"]["text"] = args.prompt
        if args.negative is not None:
            workflow["3"]["inputs"]["text"] = args.negative
        workflow["13"]["inputs"]["filename_prefix"] = f"{args.prefix}_seed{seed}"

        print(f"[run_inpaint] seed={seed} steps={args.steps} cfg={args.cfg} "
              f"controlnet_strength={args.controlnet_strength}")
        print(f"[run_inpaint] prompt: {workflow['2']['inputs']['text']!r}")
        paths = run_workflow(workflow, output_dir=OUTPUT_DIR, timeout=300.0)
        all_paths.extend(paths)

    print(f"[run_inpaint] 完了: {len(all_paths)}枚")
    for p in all_paths:
        print(f"  - {p}")


if __name__ == "__main__":
    main()
