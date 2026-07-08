"""ComfyUI headless API 疎通確認 + 再利用可能ヘルパー。

ComfyUI本体は本リポジトリ外（E:\\ComfyUI）にインストールされている前提。
サーバーを起動した状態で実行する:

    E:\\ComfyUI\\venv\\Scripts\\python.exe E:\\ComfyUI\\main.py

このスクリプトは:
1. 最小構成のSDXL text-to-imageワークフロー（API Format JSON、本ファイルと同じ
   ディレクトリの `sdxl_txt2img_api.json` に保存済み）を読み込み、
2. http://127.0.0.1:8188/prompt にPOSTしてキューに投入し、
3. /history/{prompt_id} をポーリングして完了を待ち、
4. /view エンドポイントから生成画像を取得してローカルに保存する。

観点1（3Dモデル参考画像 + ControlNet差分比較）・観点2（inpaintingによる周辺装飾）の
PoCでも、run_workflow() / queue_prompt() / fetch_image() をそのまま再利用できる。

使い方（動作確認）:
    python comfyui_api_test.py
    python comfyui_api_test.py --prompt "a red brick station building, isometric view" --seed 42
"""

from __future__ import annotations

import argparse
import copy
import json
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any

COMFYUI_HOST = "127.0.0.1"
COMFYUI_PORT = 8188
BASE_URL = f"http://{COMFYUI_HOST}:{COMFYUI_PORT}"

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_WORKFLOW_PATH = SCRIPT_DIR / "sdxl_txt2img_api.json"
DEFAULT_OUTPUT_DIR = SCRIPT_DIR / "output"


def load_workflow(path: Path = DEFAULT_WORKFLOW_PATH) -> dict[str, Any]:
    """API Format のワークフローJSONを読み込む。"""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def queue_prompt(workflow: dict[str, Any], client_id: str) -> str:
    """ワークフローを /prompt にPOSTしてキューに投入し、prompt_id を返す。"""
    payload = json.dumps({"prompt": workflow, "client_id": client_id}).encode("utf-8")
    req = urllib.request.Request(
        f"{BASE_URL}/prompt", data=payload, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        # ComfyUI はノード検証エラー時 400 + 詳細JSONを返す
        detail = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"ComfyUI がワークフローを拒否しました: {detail}") from e
    return body["prompt_id"]


def wait_for_completion(prompt_id: str, timeout: float = 300.0, poll_interval: float = 1.0) -> dict[str, Any]:
    """/history/{prompt_id} をポーリングし、実行完了後の history エントリを返す。"""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with urllib.request.urlopen(f"{BASE_URL}/history/{prompt_id}", timeout=30) as resp:
            history = json.loads(resp.read())
        if prompt_id in history:
            entry = history[prompt_id]
            status = entry.get("status", {})
            if status.get("completed") is True or status.get("status_str") == "success":
                return entry
            if status.get("status_str") == "error":
                raise RuntimeError(f"ComfyUI 実行がエラーで終了しました: {status}")
        time.sleep(poll_interval)
    raise TimeoutError(f"prompt_id={prompt_id} の完了を {timeout}秒待っても確認できませんでした")


def fetch_image(filename: str, subfolder: str, folder_type: str) -> bytes:
    """/view エンドポイントから生成画像のバイト列を取得する。"""
    from urllib.parse import urlencode

    query = urlencode({"filename": filename, "subfolder": subfolder, "type": folder_type})
    with urllib.request.urlopen(f"{BASE_URL}/view?{query}", timeout=30) as resp:
        return resp.read()


def run_workflow(
    workflow: dict[str, Any],
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    timeout: float = 300.0,
) -> list[Path]:
    """ワークフローを実行し、生成された画像をすべて output_dir に保存してパス一覧を返す。

    観点1/観点2 のPoCから直接呼び出すためのメイン関数。
    workflow は load_workflow() で読み込んだ dict をコピーして
    ノードの text / seed / 画像パス等を書き換えてから渡すこと。
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    client_id = str(uuid.uuid4())

    prompt_id = queue_prompt(workflow, client_id)
    print(f"[queue_prompt] prompt_id={prompt_id}")

    entry = wait_for_completion(prompt_id, timeout=timeout)

    saved_paths: list[Path] = []
    outputs = entry.get("outputs", {})
    for node_id, node_output in outputs.items():
        for img in node_output.get("images", []):
            data = fetch_image(img["filename"], img.get("subfolder", ""), img.get("type", "output"))
            out_path = output_dir / img["filename"]
            out_path.write_bytes(data)
            saved_paths.append(out_path)
            print(f"[fetch_image] saved: {out_path} ({len(data)} bytes)")

    return saved_paths


def check_server_alive() -> bool:
    """ComfyUIサーバーが起動しているか（/system_stats疎通）を確認する。"""
    try:
        with urllib.request.urlopen(f"{BASE_URL}/system_stats", timeout=5) as resp:
            stats = json.loads(resp.read())
        devices = stats.get("devices", [])
        if devices:
            print(f"[check_server_alive] GPU: {devices[0].get('name')}, "
                  f"VRAM free: {devices[0].get('vram_free', 0) / 1e9:.2f} GB")
        return True
    except (urllib.error.URLError, ConnectionRefusedError, TimeoutError):
        return False


def main() -> None:
    parser = argparse.ArgumentParser(description="ComfyUI /prompt API 疎通確認スクリプト")
    parser.add_argument(
        "--prompt", default="a simple wooden train station building, isometric view, clean background",
        help="positive prompt (CLIPTextEncode の text を上書きする)",
    )
    parser.add_argument("--negative", default="blurry, low quality, text, watermark")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--steps", type=int, default=20)
    parser.add_argument("--workflow", type=Path, default=DEFAULT_WORKFLOW_PATH)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()

    print(f"[main] ComfyUI疎通確認: {BASE_URL}")
    if not check_server_alive():
        raise SystemExit(
            f"ComfyUIサーバーに接続できません（{BASE_URL}）。\n"
            r"E:\ComfyUI\venv\Scripts\python.exe E:\ComfyUI\main.py を起動してから再実行してください。"
        )
    print("[main] サーバー疎通OK")

    workflow = load_workflow(args.workflow)
    workflow = copy.deepcopy(workflow)

    # ノードID "6"=positive prompt, "7"=negative prompt, "3"=KSampler
    # （sdxl_txt2img_api.json のノード構成に合わせた固定インデックス。詳細はJSON参照）
    workflow["6"]["inputs"]["text"] = args.prompt
    workflow["7"]["inputs"]["text"] = args.negative
    workflow["3"]["inputs"]["seed"] = args.seed
    workflow["3"]["inputs"]["steps"] = args.steps

    print(f"[main] prompt: {args.prompt!r}")
    print(f"[main] negative: {args.negative!r}")
    print(f"[main] seed={args.seed} steps={args.steps}")

    paths = run_workflow(workflow, output_dir=args.output_dir)

    if paths:
        print(f"[main] 成功: {len(paths)}枚の画像を生成しました")
        for p in paths:
            print(f"  - {p}")
    else:
        raise SystemExit("[main] 画像が1枚も生成されませんでした（ワークフロー構成を確認してください）")


if __name__ == "__main__":
    main()
