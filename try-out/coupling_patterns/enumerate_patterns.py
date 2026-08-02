#!/usr/bin/env python3
"""vehicle dat から連結制約(constraint[prev/next])を読み、可能な編成パターンを列挙するPoC。

ループ（自己参照・相互参照）がある場合、理論上は無限に編成パターンが存在するため、
--max-len（デフォルト6両）で打ち切って列挙する。ループに関与する車両は事前に
強連結成分(SCC)解析で検出し、警告として表示する。

refs/simutrans-dat-linter/src/couplings.rs と同じ制約表現を読むが、あちらは
「有限な編成が1つでも組み立て可能か」を判定するだけ（充足可能性判定）で、
実際のパターン列挙は行っていない。本スクリプトはこのリポジトリの try-out 用の
独立実装で、dat_linter のパーサ（値をtrimしない等のmakeobj厳密挙動の再現）は
再利用していない。
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

TERMINAL = "none"


@dataclass
class Vehicle:
    name: str
    source: str
    prev: list[str] | None  # None = 無制約（何にでも繋がる）
    next: list[str] | None

    def can_be_first(self) -> bool:
        return self.prev is None or TERMINAL in self.prev

    def can_be_last(self) -> bool:
        return self.next is None or TERMINAL in self.next


def split_records(text: str) -> list[dict[str, str]]:
    """1ファイルに複数のobj定義が`-`区切り行で連結されているケースに対応する。

    dat_linter (refs/simutrans-dat-linter/src/parser.rs の parse_records) と同じ
    区切りルール: 行頭が`-`の行に達するたびにそれまでの1レコードを確定する
    （空のまま区切り行に達したレコードは読み飛ばす）。重複キーは real makeobj
    (tabfile_t::read()) と同じく**先勝ち**（後から出てきた同名キーは無視）。
    """
    records: list[dict[str, str]] = []
    kv: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("-"):
            if kv:
                records.append(kv)
                kv = {}
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip().lower()
        if key not in kv:  # 先勝ち
            kv[key] = value.strip()
    if kv:
        records.append(kv)
    return records


def parse_dat(path: Path) -> list[Vehicle]:
    records = split_records(path.read_text(encoding="utf-8"))
    total = len(records)
    vehicles = []
    for idx, kv in enumerate(records):
        if kv.get("obj") != "vehicle":
            continue
        name = kv.get("name", "")
        if not name:
            raise ValueError(f"{path}: obj=vehicle に name がありません")
        source = f"{path} [{idx + 1}/{total}]" if total > 1 else str(path)

        def read_side(side: str, kv: dict[str, str] = kv) -> list[str] | None:
            options = []
            i = 0
            while True:
                key = f"constraint[{side}][{i}]"
                if key not in kv or kv[key] == "":
                    break
                raw = kv[key]
                options.append(TERMINAL if raw.lower() == TERMINAL else raw)
                i += 1
            return options or None

        vehicles.append(
            Vehicle(name=name, source=source, prev=read_side("prev"), next=read_side("next"))
        )
    return vehicles


def load_vehicles(directory: Path) -> list[Vehicle]:
    vehicles: list[Vehicle] = []
    for path in sorted(directory.glob("*.dat")):
        vehicles.extend(parse_dat(path))
    return vehicles


def edge(x: Vehicle, y: Vehicle) -> bool:
    x_allows_next = x.next is None or y.name in x.next
    y_allows_prev = y.prev is None or x.name in y.prev
    return x_allows_next and y_allows_prev


def find_cyclic_groups(vehicles: list[Vehicle]) -> list[list[str]]:
    """強連結成分(SCC)がサイズ>1、または自己ループを持つ車両グループを検出する。

    Tarjanのアルゴリズム。これらのグループを通過する編成は両数の上限なしには
    列挙が終わらない（無限に存在する）ため、列挙前に警告として提示する。
    """
    names = [v.name for v in vehicles]
    index = {v.name: v for v in vehicles}
    adj = {n: [m for m in names if edge(index[n], index[m])] for n in names}

    counter = [0]
    stack: list[str] = []
    on_stack: set[str] = set()
    indices: dict[str, int] = {}
    low: dict[str, int] = {}
    sccs: list[list[str]] = []

    def strongconnect(v: str):
        indices[v] = counter[0]
        low[v] = counter[0]
        counter[0] += 1
        stack.append(v)
        on_stack.add(v)
        for w in adj[v]:
            if w not in indices:
                strongconnect(w)
                low[v] = min(low[v], low[w])
            elif w in on_stack:
                low[v] = min(low[v], indices[w])
        if low[v] == indices[v]:
            comp = []
            while True:
                w = stack.pop()
                on_stack.discard(w)
                comp.append(w)
                if w == v:
                    break
            sccs.append(comp)

    sys.setrecursionlimit(max(1000, len(names) * 4 + 100))
    for n in names:
        if n not in indices:
            strongconnect(n)

    cyclic = []
    for comp in sccs:
        if len(comp) > 1:
            cyclic.append(sorted(comp))
        elif comp and comp[0] in adj[comp[0]]:
            cyclic.append(comp)
    return cyclic


def find_unconstrained_next(vehicles: list[Vehicle]) -> list[str]:
    """constraint[next]自体が存在しない（=無制約）車両名の一覧。

    このディレクトリ内の車両に限らず、ゲーム内のどの車両とも連結しうるという意味。
    ローカルの車両だけで具体的な組み合わせを列挙すると「これしか繋がらない」という
    誤った印象を与えるため、列挙では `*` 1本にまとめる。
    """
    return [v.name for v in vehicles if v.next is None]


def find_dangling_next_refs(vehicles: list[Vehicle]) -> list[tuple[str, str]]:
    """constraint[next]が指す車両名がこのディレクトリ内に存在しない（dangling）組を返す。

    makeobj自身は参照先車両名の実在性を検証しない（解決はゲーム読み込み時まで遅延される。
    refs/simutrans-dat-linter/src/couplings.rs の check_dangling_refs と同じ観点）ため、
    このスクリプトの手元データだけでは相手側の constraint[prev] が本当にこの車両を
    受け入れるか判断できない。
    """
    known = {v.name for v in vehicles}
    out = []
    for v in vehicles:
        if v.next is None:
            continue
        for opt in v.next:
            if opt != TERMINAL and opt not in known:
                out.append((v.name, opt))
    return out


def enumerate_patterns(
    vehicles: list[Vehicle], max_len: int, max_results: int
) -> tuple[list[list[str]], bool]:
    """短い編成から順に(両数ごとに)広げていく幅優先探索でmax_len両まで列挙する。

    ループがあっても max_len が上限になるため必ず停止する。
    深さ優先だと「ループを何周もした長い編成」を先に使い果たしてしまい、
    --max-results に達した時点で自然な短い編成が結果に含まれないことがあるため、
    両数の短い順に確定させる幅優先探索にしている（実際のpaksetアドオンで確認した挙動）。

    無制約の車両（constraint[next]自体が無い）に到達した場合は、以降の相手を
    具体的に列挙せず `*` を付けて打ち切る（例: "A-B-*"）。
    dangling参照（constraint[next]が指す車両がこのディレクトリに無い）の場合は、
    相手側の受け入れ可否が不明なため `?` を付けて打ち切る（例: "A-D?"）。

    戻り値: (列挙できたパターンのリスト, max_len/max_resultsで打ち切りが発生したか)
    """
    index = {v.name: v for v in vehicles}
    known_names = set(index)
    results: list[list[str]] = []
    truncated = [False]
    # 分岐の多いループを含むデータで frontier 自体が爆発しないようにする上限
    frontier_cap = max(max_results * 20, 1000)

    def add_result(p: list[str]) -> bool:
        if len(results) >= max_results:
            truncated[0] = True
            return False
        results.append(list(p))
        return True

    frontier = [[v.name] for v in vehicles if v.can_be_first()]
    length = 1
    while frontier and length <= max_len:
        next_frontier: list[list[str]] = []
        for path in frontier:
            if len(results) >= max_results:
                truncated[0] = True
                break
            current = index[path[-1]]
            if current.can_be_last() and not add_result(path):
                break
            if length >= max_len:
                if any(edge(current, v) for v in vehicles):
                    truncated[0] = True
                continue
            if current.next is None:
                # 無制約: 個々の相手は列挙せず "*" 1本で打ち切る
                add_result(path + ["*"])
                continue
            for opt in current.next:
                if opt != TERMINAL and opt not in known_names:
                    # dangling参照: 相手の制約が不明なのでここで打ち切る
                    add_result(path + [f"{opt}?"])
            for v in vehicles:
                if edge(current, v):
                    next_frontier.append(path + [v.name])
        if len(next_frontier) > frontier_cap:
            next_frontier = next_frontier[:frontier_cap]
            truncated[0] = True
        frontier = next_frontier
        length += 1

    return results, truncated[0]


def format_pattern(path: list[str]) -> str:
    """編成1件を表示用文字列に整形する。

    実際のpaksetアドオンでは車両名が長く(系列名を含む)、同じ編成内でその系列名部分が
    毎両繰り返されて読みにくい（例:
    "odakyu1000_(Wide-door)_TcFront-odakyu1000_(Wide-door)_M4-...-odakyu1000_(Wide-door)_TcBack"）。
    パス内の実車両名（"*"や"D?"のようなマーカーは除く）に共通する先頭部分があれば、
    それを1回だけ出して各両は差分（役割名）だけを`[...]`内に並べる
    （例: "odakyu1000_(Wide-door)_[TcFront-M4-M5-TcBack]"）。圧縮しても実質的に
    短くならない場合（短い編成、系列がバラバラ等）はそのまま`-`区切りで表示する。
    """
    real_names = [t[:-1] if t.endswith("?") else t for t in path if t != "*"]
    plain = "-".join(path)
    if len(real_names) < 2:
        return plain

    prefix = real_names[0]
    for name in real_names[1:]:
        limit = min(len(prefix), len(name))
        i = 0
        while i < limit and prefix[i] == name[i]:
            i += 1
        prefix = prefix[:i]
        if not prefix:
            return plain

    # "odakyu1000_(Wide-door" (=`(`が閉じられる前で切れる)のように括弧の途中で切れると
    # "odakyu1000_(Wide-door[)_TcFront-..." のように開き括弧と閉じ括弧が[...]を挟んで
    # 分断され、かえって読みにくくなる。`(`の対応が取れる長さまで後退させる
    while prefix and prefix.count("(") != prefix.count(")"):
        prefix = prefix[:-1]
    if not prefix:
        return plain

    if any(len(name) == len(prefix) for name in real_names):
        return plain  # いずれかの車両名がprefixそのもの(接尾辞が空)になるケースは避ける

    parts = []
    for t in path:
        if t == "*":
            parts.append("*")
        elif t.endswith("?"):
            parts.append(t[len(prefix):-1] + "?")
        else:
            parts.append(t[len(prefix):])
    compressed = f"{prefix}[{'-'.join(parts)}]"
    return compressed if len(compressed) < len(plain) else plain


def print_truncated(names: list[str], limit: int = 12, indent: str = "  - "):
    for name in names[:limit]:
        print(f"{indent}{name}")
    if len(names) > limit:
        print(f"{indent}...ほか{len(names) - limit}件")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--max-len", type=int, default=6, help="列挙する編成の最大両数（デフォルト6）")
    parser.add_argument(
        "--max-results", type=int, default=200, help="列挙する編成パターン数の上限（デフォルト200）"
    )
    args = parser.parse_args()

    vehicles = load_vehicles(args.directory)
    if not vehicles:
        print(f"{args.directory}: obj=vehicle が見つかりませんでした", file=sys.stderr)
        sys.exit(1)

    cyclic = find_cyclic_groups(vehicles)
    if cyclic:
        print("[警告] 以下の車両グループは連結がループしており、理論上は無限に編成パターンが存在します:")
        for group in cyclic:
            print(f"  - ({len(group)}両のグループ) {', '.join(group[:12])}"
                  + (f", ...ほか{len(group) - 12}件" if len(group) > 12 else ""))
        print(f"  -> 以下は --max-len={args.max_len} 両までで打ち切った一部の例です\n")

    unconstrained = find_unconstrained_next(vehicles)
    if unconstrained:
        print("[情報] 以下の車両は連結相手の制約(constraint[next])が無く、どの車両とも連結しえます"
              "（一覧では相手を列挙せず \"*\" で表します）:")
        print_truncated(unconstrained)
        print()

    dangling = find_dangling_next_refs(vehicles)
    if dangling:
        print("[警告] 以下の連結指定は、参照先の車両がこのディレクトリに存在しません"
              "（相手側の constraint[prev] を確認できないため、一覧では \"?\" を付けて打ち切ります）:")
        print_truncated([f"{name} -> {target}" for name, target in dangling])
        print()

    results, truncated = enumerate_patterns(vehicles, args.max_len, args.max_results)
    results.sort(key=lambda p: (len(p), p))

    print(f"{len(results)} 件の編成パターン (--max-len={args.max_len}):")
    if results:
        print("  (車両名の共通する先頭部分は 先頭部分[差分-差分-...] の形にまとめて表示しています)")
    for p in results:
        print("  " + format_pattern(p))

    if truncated:
        print(
            f"\n[注意] --max-len={args.max_len} または --max-results={args.max_results} により"
            f"打ち切られました。実際にはさらに多くの（ループがあれば無限の）パターンが存在します。"
        )


if __name__ == "__main__":
    main()
