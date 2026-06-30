mod diagnostics;
mod formatter;
mod parser;
mod rules;
mod vehicle;

use diagnostics::Severity;
use parser::DatFile;
use std::path::Path;
use std::process::ExitCode;

fn main() -> ExitCode {
    let mut args: Vec<String> = std::env::args().skip(1).collect();

    if !args.is_empty() && args[0] == "fmt" {
        args.remove(0);
        return run_fmt(&args);
    }
    if !args.is_empty() && args[0] == "couplings" {
        args.remove(0);
        return run_couplings(&args);
    }
    if !args.is_empty() && args[0] == "lint" {
        args.remove(0);
    }
    run_lint(&args)
}

fn run_lint(args: &[String]) -> ExitCode {
    let mut path_arg: Option<&str> = None;
    let mut verbosity: u8 = 0;
    for arg in args {
        match arg.as_str() {
            // -v: info まで表示 / -vv: debug まで表示
            "-v" | "--verbose" => verbosity = verbosity.max(1),
            "-vv" => verbosity = verbosity.max(2),
            other => path_arg = Some(other),
        }
    }

    let Some(path_arg) = path_arg else {
        eprintln!("usage: dat_linter [lint] [-v|-vv] <path/to/file.dat>");
        return ExitCode::FAILURE;
    };
    let level = Severity::from_verbosity(verbosity);

    let path = Path::new(path_arg);
    let dat = match DatFile::parse(path) {
        Ok(d) => d,
        Err(e) => {
            eprintln!("{}: 読み込みに失敗しました ({e})", path.display());
            return ExitCode::FAILURE;
        }
    };

    let obj_type = dat.get("obj").unwrap_or("");
    if obj_type != "building" {
        eprintln!(
            "{}: obj={obj_type} は未対応です。このPoCは obj=building のみ検証できます",
            path.display()
        );
        return ExitCode::FAILURE;
    }

    let dat_dir = path.parent().unwrap_or_else(|| Path::new("."));
    let diags = rules::check_building(&dat, dat_dir);

    for d in diags.iter().filter(|d| d.severity <= level) {
        println!("{}: {d}", path.display());
    }

    let error_count = diags.iter().filter(|d| d.severity == Severity::Error).count();
    let warning_count = diags
        .iter()
        .filter(|d| d.severity == Severity::Warning)
        .count();

    if error_count == 0 && warning_count == 0 {
        println!("{}: OK（既知ルールの範囲では問題なし）", path.display());
    } else {
        println!(
            "{}: error {error_count} 件 / warning {warning_count} 件",
            path.display()
        );
    }

    if error_count > 0 {
        ExitCode::FAILURE
    } else {
        ExitCode::SUCCESS
    }
}

fn run_fmt(args: &[String]) -> ExitCode {
    let mut path_arg: Option<&str> = None;
    let mut reorder = false;
    let mut write = false;
    for arg in args {
        match arg.as_str() {
            "--reorder" => reorder = true,
            "--write" | "-w" => write = true,
            other => path_arg = Some(other),
        }
    }

    let Some(path_arg) = path_arg else {
        eprintln!("usage: dat_linter fmt [--reorder] [--write] <path/to/file.dat>");
        return ExitCode::FAILURE;
    };
    let path = Path::new(path_arg);

    let text = match std::fs::read_to_string(path) {
        Ok(t) => t,
        Err(e) => {
            eprintln!("{}: 読み込みに失敗しました ({e})", path.display());
            return ExitCode::FAILURE;
        }
    };

    let parsed = formatter::parse_entries(&text);
    for w in &parsed.warnings {
        eprintln!("{}: {w}", path.display());
    }

    let formatted = if reorder {
        let (out, warnings) = formatter::format_reordered(&parsed.entries);
        for w in &warnings {
            eprintln!("{}: {w}", path.display());
        }
        out
    } else {
        formatter::format_preserve_order(&parsed.entries)
    };

    if write {
        if let Err(e) = std::fs::write(path, &formatted) {
            eprintln!("{}: 書き込みに失敗しました ({e})", path.display());
            return ExitCode::FAILURE;
        }
        eprintln!("{}: フォーマット結果を書き込みました", path.display());
    } else {
        print!("{formatted}");
    }

    ExitCode::SUCCESS
}

/// 静的解析(PHPStan的な層)のPoC: 1ディレクトリ内の vehicle dat 群を読み込み、
/// (1) makeobjが検証しないconstraint参照の実在性、(2) 連結制約の充足可能性
/// （有限な編成として絶対に成立しない車両が無いか）を検査する。
fn run_couplings(args: &[String]) -> ExitCode {
    let Some(dir_arg) = args.first() else {
        eprintln!("usage: dat_linter couplings <path/to/vehicle_dat_dir>");
        return ExitCode::FAILURE;
    };
    let dir = Path::new(dir_arg);

    let (vehicles, mut diags) = vehicle::load_vehicles(dir);
    diags.extend(vehicle::check_dangling_refs(&vehicles));
    diags.extend(vehicle::check_satisfiability(&vehicles));

    println!("{}: {} 台の vehicle dat を読み込みました", dir.display(), vehicles.len());
    for d in &diags {
        println!("{}: {d}", dir.display());
    }

    let error_count = diags.iter().filter(|d| d.severity == Severity::Error).count();
    if error_count == 0 {
        println!("{}: OK（既知ルールの範囲では問題なし）", dir.display());
    } else {
        println!("{}: error {error_count} 件", dir.display());
    }

    if error_count > 0 {
        ExitCode::FAILURE
    } else {
        ExitCode::SUCCESS
    }
}
