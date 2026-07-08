"""
canny ControlNet（SDXL）で isometric建物のcontrolnet生成を複数パターン試すランナー。

try-out/t2i_research/comfyui_api_test.py の run_workflow() 等をそのまま再利用する。

Usage:
    python run_controlnet_poc.py
"""

from __future__ import annotations

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

# 2026-07-08 フィードバック対応: 影(cast shadow)抑制のため、各プロンプトに
# "flat lighting, no shadow, clean silhouette" 系の語を追加（negative側は
# sdxl_controlnet_canny_api.json のnode 7側で共通に shadow系ネガティブを追加済み）。
# filename_prefixに _noshadow を付け、旧版(影あり)の生成結果と見比べられるようにした。
PROMPTS = [
    {
        "name": "wooden_station_noshadow",
        "seed": 42,
        "text": (
            "a small wooden train station building with a tiled gable roof, "
            "isometric game asset, flat lighting, no shadow, no cast shadow, "
            "clean silhouette, detailed wood siding, simple flat background, "
            "no ground, no floor"
        ),
    },
    {
        "name": "brick_cottage_noshadow",
        "seed": 123,
        "text": (
            "a small red brick cottage house with a terracotta tiled gable roof, "
            "isometric game asset, cute low-poly style, flat lighting, no shadow, "
            "no cast shadow, clean silhouette, simple flat background, no ground, no floor"
        ),
    },
    {
        "name": "stone_shrine_noshadow",
        "seed": 777,
        "text": (
            "a small Japanese stone shrine building with a dark tiled gable roof, "
            "isometric game asset, weathered stone walls, wooden beams, flat lighting, "
            "no shadow, no cast shadow, clean silhouette, simple flat background, "
            "no ground, no floor"
        ),
    },
]


def main() -> None:
    print("[main] ComfyUI疎通確認")
    if not check_server_alive():
        raise SystemExit("ComfyUIサーバーに接続できません。先に起動してください。")
    print("[main] サーバー疎通OK")

    base_workflow = load_workflow(WORKFLOW_PATH)

    for p in PROMPTS:
        workflow = copy.deepcopy(base_workflow)
        workflow["6"]["inputs"]["text"] = p["text"]
        workflow["3"]["inputs"]["seed"] = p["seed"]
        workflow["9"]["inputs"]["filename_prefix"] = f"t2i_iso_poc_canny_{p['name']}"

        print(f"\n[main] === pattern: {p['name']} (seed={p['seed']}) ===")
        print(f"[main] prompt: {p['text']!r}")
        paths = run_workflow(workflow, output_dir=OUTPUT_DIR, timeout=300.0)
        for path in paths:
            print(f"  -> {path}")


if __name__ == "__main__":
    main()
