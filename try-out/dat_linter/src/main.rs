mod diagnostics;
mod parser;
mod rules;

use diagnostics::Severity;
use parser::DatFile;
use std::path::Path;
use std::process::ExitCode;

fn main() -> ExitCode {
    let mut path_arg: Option<String> = None;
    let mut verbosity: u8 = 0;
    for arg in std::env::args().skip(1) {
        match arg.as_str() {
            // -v: info まで表示 / -vv: debug まで表示
            "-v" | "--verbose" => verbosity = verbosity.max(1),
            "-vv" => verbosity = verbosity.max(2),
            other => path_arg = Some(other.to_string()),
        }
    }

    let Some(path_arg) = path_arg else {
        eprintln!("usage: dat_linter [-v|-vv] <path/to/file.dat>");
        return ExitCode::FAILURE;
    };
    let level = Severity::from_verbosity(verbosity);

    let path = Path::new(&path_arg);
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
