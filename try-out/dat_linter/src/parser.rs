use std::collections::BTreeMap;
use std::fs;
use std::path::Path;

/// 簡易 .dat パーサ。makeobj の tabfile_t::format_key() を模倣する:
/// キーは前後空白をトリムして小文字化、'[' 'と']'の間の空白は除去する。
pub struct DatFile {
    pub pairs: BTreeMap<String, String>,
}

impl DatFile {
    pub fn parse(path: &Path) -> std::io::Result<Self> {
        let text = fs::read_to_string(path)?;
        let mut pairs = BTreeMap::new();

        for raw_line in text.lines() {
            let line = raw_line.trim_end_matches('\r');
            if line.is_empty() || line.starts_with('#') || line.starts_with(' ') {
                continue;
            }
            let Some((key_raw, value)) = line.split_once('=') else {
                continue;
            };
            let key = format_key(key_raw);
            pairs.insert(key, value.trim().to_string());
        }

        Ok(DatFile { pairs })
    }

    pub fn get(&self, key: &str) -> Option<&str> {
        self.pairs.get(key).map(|s| s.as_str())
    }

    pub fn get_ints(&self, key: &str) -> Vec<i64> {
        match self.get(key) {
            Some(v) => v
                .split(',')
                .filter_map(|s| s.trim().parse::<i64>().ok())
                .collect(),
            None => Vec::new(),
        }
    }
}

fn format_key(raw: &str) -> String {
    let trimmed = raw.trim_end();
    let mut out = String::with_capacity(trimmed.len());
    let mut in_bracket = false;
    for c in trimmed.chars() {
        match c {
            '[' => {
                in_bracket = true;
                out.push(c);
            }
            ']' => {
                in_bracket = false;
                out.push(c);
            }
            ' ' if in_bracket => {}
            _ => out.push(c.to_ascii_lowercase()),
        }
    }
    out
}
