use crate::diagnostics::Diagnostic;
use crate::parser::DatFile;
use std::collections::{BTreeSet, VecDeque};
use std::path::Path;

/// vehicle_writer.cc の `constraint[prev][N]`/`constraint[next][N]` を表現する。
/// "none" は「これ以上前/後ろが無くてよい（先頭/末尾でよい）」という特別な選択肢で、
/// xref_writer.cc を見るとmakeobj自身は参照先車両名の実在性を検証しない
/// （解決はゲーム読み込み時まで遅延される）。
#[derive(Clone, PartialEq, Eq, Debug)]
pub enum ConstraintOption {
    /// "none": prev側なら「先頭でよい」、next側なら「末尾でよい」
    Terminal,
    Named(String),
}

#[derive(Clone)]
pub enum ConstraintSide {
    /// constraint[prev/next][0]が1つも無い = 無制約（何でも前後につけられる）
    Unconstrained,
    Options(Vec<ConstraintOption>),
}

pub struct VehicleInfo {
    pub name: String,
    pub source: String,
    pub prev: ConstraintSide,
    pub next: ConstraintSide,
}

pub fn load_vehicles(dir: &Path) -> (Vec<VehicleInfo>, Vec<Diagnostic>) {
    let mut vehicles = Vec::new();
    let mut diags = Vec::new();

    let mut entries: Vec<_> = match std::fs::read_dir(dir) {
        Ok(rd) => rd.filter_map(|e| e.ok()).collect(),
        Err(e) => {
            diags.push(Diagnostic::error(
                "read-dir-failed",
                format!("{}: ディレクトリを読めません ({e})", dir.display()),
            ));
            return (vehicles, diags);
        }
    };
    entries.sort_by_key(|e| e.path());

    for entry in entries {
        let path = entry.path();
        if path.extension().and_then(|s| s.to_str()) != Some("dat") {
            continue;
        }
        let dat = match DatFile::parse(&path) {
            Ok(d) => d,
            Err(e) => {
                diags.push(Diagnostic::error(
                    "read-failed",
                    format!("{}: 読み込みに失敗しました ({e})", path.display()),
                ));
                continue;
            }
        };
        if dat.get("obj").unwrap_or("") != "vehicle" {
            continue;
        }
        let name = dat.get("name").unwrap_or("").to_string();
        if name.is_empty() {
            diags.push(Diagnostic::error(
                "missing-name",
                format!("{}: obj=vehicle に name がありません", path.display()),
            ));
            continue;
        }

        vehicles.push(VehicleInfo {
            prev: read_constraint_side(&dat, "prev"),
            next: read_constraint_side(&dat, "next"),
            source: path.display().to_string(),
            name,
        });
    }

    (vehicles, diags)
}

fn read_constraint_side(dat: &DatFile, side: &str) -> ConstraintSide {
    let mut options = Vec::new();
    let mut i = 0;
    loop {
        let key = format!("constraint[{side}][{i}]");
        let Some(raw) = dat.get(&key) else {
            break;
        };
        if raw.eq_ignore_ascii_case("none") {
            options.push(ConstraintOption::Terminal);
        } else {
            options.push(ConstraintOption::Named(raw.to_string()));
        }
        i += 1;
    }
    if options.is_empty() {
        ConstraintSide::Unconstrained
    } else {
        ConstraintSide::Options(options)
    }
}

/// linter相当の検査: makeobjが検証しない車両名参照の実在性をパークセット内で確認する。
pub fn check_dangling_refs(vehicles: &[VehicleInfo]) -> Vec<Diagnostic> {
    let known: BTreeSet<&str> = vehicles.iter().map(|v| v.name.as_str()).collect();
    let mut diags = Vec::new();
    for v in vehicles {
        for (side_label, side) in [("prev", &v.prev), ("next", &v.next)] {
            let ConstraintSide::Options(opts) = side else {
                continue;
            };
            for opt in opts {
                if let ConstraintOption::Named(n) = opt {
                    if !known.contains(n.as_str()) {
                        diags.push(Diagnostic::error(
                            "dangling-vehicle-constraint",
                            format!(
                                "{} ({}): constraint[{side_label}]が参照する車両 \"{n}\" がこのディレクトリ内に存在しません（makeobjは参照の実在性を検証しないため、ゲーム読み込み時まで気づけません）",
                                v.name, v.source
                            ),
                        ));
                    }
                }
            }
        }
    }
    diags
}

/// 静的解析相当の検査: 「この車両を含む有限な編成が1つでも組み立て可能か」を
/// 制約グラフの到達可能性問題として解く。
/// START -> (先頭になれる車両) -> ... -> (末尾になれる車両) -> END という
/// 仮想グラフを作り、各車両がSTARTから到達可能かつENDに到達可能かを判定する。
/// 自身・参照車両の制約だけで矛盾なく組める実例が無い場合、ゲーム内で
/// 編成を組もうとしても永遠に成立しないという問題をビルド不要で発見できる。
pub fn check_satisfiability(vehicles: &[VehicleInfo]) -> Vec<Diagnostic> {
    let n = vehicles.len();

    let can_be_first = |v: &VehicleInfo| match &v.prev {
        ConstraintSide::Unconstrained => true,
        ConstraintSide::Options(opts) => opts.contains(&ConstraintOption::Terminal),
    };
    let can_be_last = |v: &VehicleInfo| match &v.next {
        ConstraintSide::Unconstrained => true,
        ConstraintSide::Options(opts) => opts.contains(&ConstraintOption::Terminal),
    };
    // X -> Y(Xの直後にYが来る)が有効なのは、Xがnextとして許し、かつYがprevとして許す場合
    let edge = |x: &VehicleInfo, y: &VehicleInfo| {
        let x_allows_next = match &x.next {
            ConstraintSide::Unconstrained => true,
            ConstraintSide::Options(opts) => opts
                .iter()
                .any(|o| matches!(o, ConstraintOption::Named(n) if n == &y.name)),
        };
        let y_allows_prev = match &y.prev {
            ConstraintSide::Unconstrained => true,
            ConstraintSide::Options(opts) => opts
                .iter()
                .any(|o| matches!(o, ConstraintOption::Named(n) if n == &x.name)),
        };
        x_allows_next && y_allows_prev
    };

    let mut reachable_from_start = vec![false; n];
    let mut queue: VecDeque<usize> = VecDeque::new();
    for (i, v) in vehicles.iter().enumerate() {
        if can_be_first(v) {
            reachable_from_start[i] = true;
            queue.push_back(i);
        }
    }
    while let Some(i) = queue.pop_front() {
        for j in 0..n {
            if !reachable_from_start[j] && edge(&vehicles[i], &vehicles[j]) {
                reachable_from_start[j] = true;
                queue.push_back(j);
            }
        }
    }

    let mut can_reach_end = vec![false; n];
    let mut queue: VecDeque<usize> = VecDeque::new();
    for (i, v) in vehicles.iter().enumerate() {
        if can_be_last(v) {
            can_reach_end[i] = true;
            queue.push_back(i);
        }
    }
    while let Some(j) = queue.pop_front() {
        for i in 0..n {
            if !can_reach_end[i] && edge(&vehicles[i], &vehicles[j]) {
                can_reach_end[i] = true;
                queue.push_back(i);
            }
        }
    }

    let mut diags = Vec::new();
    for (i, v) in vehicles.iter().enumerate() {
        if !(reachable_from_start[i] && can_reach_end[i]) {
            diags.push(Diagnostic::error(
                "unsatisfiable-constraint",
                format!(
                    "{} ({}): constraint[prev]/constraint[next]を満たす有限な編成が1つも組み立てられません（自身および参照車両の制約だけでは先頭〜末尾まで到達できない）",
                    v.name, v.source
                ),
            ));
        }
    }
    diags
}
