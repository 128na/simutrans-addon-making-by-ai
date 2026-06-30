mod diagnostics;
mod parser;
mod rules;

use diagnostics::Severity;
use parser::DatFile;
use std::path::Path;
use std::process::ExitCode;

fn main() -> ExitCode {
    let mut args = std::env::args().skip(1);
    let Some(path_arg) = args.next() else {
        eprintln!("usage: dat_linter <path/to/file.dat>");
        return ExitCode::FAILURE;
    };

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

    if diags.is_empty() {
        println!("{}: OK（既知ルールの範囲では問題なし）", path.display());
        return ExitCode::SUCCESS;
    }

    let mut has_error = false;
    for d in &diags {
        println!("{}: {d}", path.display());
        if d.severity == Severity::Error {
            has_error = true;
        }
    }
    println!(
        "{}: {} 件の問題（error含む: {}）",
        path.display(),
        diags.len(),
        has_error
    );

    if has_error {
        ExitCode::FAILURE
    } else {
        ExitCode::SUCCESS
    }
}
