use crate::parser::format_key;

/// 1行をパースした結果。tabfile_t::read()/read_line() の挙動に合わせて分類する:
/// - `#`または行頭スペースで始まる行は、実際のmakeobjでも丸ごと無視される
///   （read_line(): `while(*dest=='#' || *dest==' ')`でスキップされ続ける）。
///   フォーマッタはこれを「無効化」も「有効化」もせず、原文のまま通す
/// - `=`が無い非空行は、実際のmakeobjでも`dbg->warning("No data in ...")`になる
pub enum Entry {
    Pair { key: String, value: String },
    Comment(String),
    Blank,
    SkippedLeadingSpace(String),
    Malformed(String),
}

pub struct ParsedDat {
    pub entries: Vec<Entry>,
    pub warnings: Vec<String>,
}

pub fn parse_entries(text: &str) -> ParsedDat {
    let mut entries = Vec::new();
    let mut warnings = Vec::new();

    for (i, raw_line) in text.lines().enumerate() {
        let line = raw_line.trim_end_matches('\r');
        let lineno = i + 1;
        if line.is_empty() {
            entries.push(Entry::Blank);
        } else if line.starts_with('#') {
            entries.push(Entry::Comment(line.to_string()));
        } else if line.starts_with(' ') {
            warnings.push(format!(
                "line {lineno}: 行頭にスペースがあるため makeobj から無視されます（コメント扱い）: \"{line}\""
            ));
            entries.push(Entry::SkippedLeadingSpace(line.to_string()));
        } else if let Some((key_raw, value)) = line.split_once('=') {
            entries.push(Entry::Pair {
                key: format_key(key_raw),
                value: value.to_string(),
            });
        } else {
            warnings.push(format!(
                "line {lineno}: '=' が無いため makeobj から無視されます: \"{line}\""
            ));
            entries.push(Entry::Malformed(line.to_string()));
        }
    }

    ParsedDat { entries, warnings }
}

/// 既存の行順を保ったまま、Pair行だけ `key=value`（=前後の空白なし、値は前後トリムのみ）
/// に正規化する。コメント・スキップ行・不正行は原文のまま通す（意味を変えない）。
pub fn format_preserve_order(entries: &[Entry]) -> String {
    let mut out = String::new();
    for entry in entries {
        match entry {
            Entry::Pair { key, value } => {
                out.push_str(key);
                out.push('=');
                out.push_str(value.trim());
                out.push('\n');
            }
            Entry::Comment(s) | Entry::SkippedLeadingSpace(s) | Entry::Malformed(s) => {
                out.push_str(s);
                out.push('\n');
            }
            Entry::Blank => out.push('\n'),
        }
    }
    out
}

// building dat の「慣習的な並び」。tabfile_t::objinfo はハッシュテーブルであり
// makeobjの動作上は記述順に意味は無い（技術的な必須要件ではない）。この順序は
// try-out/station_test/station_cube.dat の実例と building_writer.cc 内で
// obj.get(...)が呼ばれる順序を参考にしたスタイル上の慣習。
const CANONICAL_ORDER: &[&str] = &[
    "obj",
    "name",
    "copyright",
    "type",
    "waytype",
    "enables_pax",
    "enables_post",
    "enables_ware",
    "level",
    "noinfo",
    "noconstruction",
    "needs_ground",
    "climates",
    "dims",
    "chance",
    "animation_time",
    "intro_year",
    "intro_month",
    "retire_year",
    "retire_month",
    "preservation_year",
    "preservation_month",
    "capacity",
    "station_capacity",
    "maintenance",
    "station_maintenance",
    "cost",
    "station_price",
    "allow_underground",
];
const CURSOR_ICON_ORDER: &[&str] = &["cursor", "icon"];

/// `--reorder`: 慣習的な並び順に再構成する。コメント・空行・スキップ行・不正行は
/// 並び替えとの整合が取れないため出力には含めない（dropした件数をwarningsで返す）。
pub fn format_reordered(entries: &[Entry]) -> (String, Vec<String>) {
    let mut warnings = Vec::new();
    let mut pairs: Vec<(&String, &String)> = Vec::new();
    let mut dropped = 0usize;

    for entry in entries {
        match entry {
            Entry::Pair { key, value } => pairs.push((key, value)),
            Entry::Blank => {}
            _ => dropped += 1,
        }
    }
    if dropped > 0 {
        warnings.push(format!(
            "--reorder: コメント/スキップ行/不正行 {dropped} 件は並び替え後の位置が一意に決まらないため出力から削除されました"
        ));
    }

    let mut known: Vec<(&String, &String)> = Vec::new();
    let mut cursor_icon: Vec<(&String, &String)> = Vec::new();
    let mut unknown: Vec<(&String, &String)> = Vec::new();
    let mut images: Vec<(&String, &String)> = Vec::new();

    for (k, v) in &pairs {
        if CANONICAL_ORDER.contains(&k.as_str()) {
            known.push((k, v));
        } else if CURSOR_ICON_ORDER.contains(&k.as_str()) {
            cursor_icon.push((k, v));
        } else if k.starts_with("frontimage[") || k.starts_with("backimage[") {
            images.push((k, v));
        } else {
            unknown.push((k, v));
        }
    }

    known.sort_by_key(|(k, _)| CANONICAL_ORDER.iter().position(|c| c == k).unwrap());
    cursor_icon.sort_by_key(|(k, _)| CURSOR_ICON_ORDER.iter().position(|c| c == k).unwrap());
    images.sort_by_key(|(k, _)| (bracket_indices(k), (*k).clone()));
    // unknown はパース順を保持（安定ソート不要、挿入順のまま）

    let mut out = String::new();
    let groups: [&[(&String, &String)]; 4] = [&known, &cursor_icon, &unknown, &images];
    let mut first_group = true;
    for group in groups {
        if group.is_empty() {
            continue;
        }
        if !first_group {
            out.push('\n');
        }
        first_group = false;
        for (k, v) in group {
            out.push_str(k);
            out.push('=');
            out.push_str(v.trim());
            out.push('\n');
        }
    }

    (out, warnings)
}

fn bracket_indices(key: &str) -> Vec<i64> {
    let Some(start) = key.find('[') else {
        return Vec::new();
    };
    key[start..]
        .trim_start_matches('[')
        .trim_end_matches(']')
        .split("][")
        .map(|s| s.parse::<i64>().unwrap_or(0))
        .collect()
}
