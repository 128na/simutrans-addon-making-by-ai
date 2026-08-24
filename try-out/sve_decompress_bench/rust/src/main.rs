use std::fs;
use std::io::Read;
use std::path::Path;
use std::time::Instant;

use bzip2_rs::DecoderReader as Bz2Reader;
use flate2::read::GzDecoder;

#[derive(Debug)]
enum Format {
    Gzip,
    Bzip2,
    Raw,
}

fn detect_format(bytes: &[u8]) -> Format {
    if bytes.len() >= 2 && bytes[0] == 0x1f && bytes[1] == 0x8b {
        Format::Gzip
    } else if bytes.len() >= 3 && &bytes[0..3] == b"BZh" {
        Format::Bzip2
    } else {
        Format::Raw
    }
}

fn version_line(bytes: &[u8]) -> String {
    let end = bytes.iter().position(|&b| b < 32).unwrap_or(bytes.len().min(64));
    String::from_utf8_lossy(&bytes[..end]).to_string()
}

fn main() {
    let save_dir = Path::new(env!("CARGO_MANIFEST_DIR")).join("../../../refs/save");

    let mut entries: Vec<_> = fs::read_dir(&save_dir)
        .unwrap_or_else(|e| panic!("cannot read {:?}: {}", save_dir, e))
        .filter_map(|e| e.ok())
        .filter(|e| e.path().extension().map(|ext| ext == "sve").unwrap_or(false))
        .collect();
    entries.sort_by_key(|e| e.path());

    println!(
        "{:<28} {:>10} {:>8} {:>12} {:>10} {:>10}",
        "file", "format", "raw_kb", "decomp_kb", "read_ms", "decomp_ms"
    );

    let mut total_read_ms = 0.0f64;
    let mut total_decomp_ms = 0.0f64;
    let mut total_raw = 0u64;
    let mut total_decomp = 0u64;

    for entry in entries {
        let path = entry.path();
        let name = path.file_name().unwrap().to_string_lossy().to_string();

        let t0 = Instant::now();
        let raw = fs::read(&path).unwrap();
        let read_ms = t0.elapsed().as_secs_f64() * 1000.0;

        let format = detect_format(&raw);

        let t1 = Instant::now();
        let decompressed = match format {
            Format::Gzip => {
                let mut decoder = GzDecoder::new(&raw[..]);
                let mut out = Vec::with_capacity(raw.len() * 6);
                decoder.read_to_end(&mut out).unwrap();
                out
            }
            Format::Bzip2 => {
                let mut decoder = Bz2Reader::new(&raw[..]);
                let mut out = Vec::with_capacity(raw.len() * 6);
                decoder.read_to_end(&mut out).unwrap();
                out
            }
            Format::Raw => raw.clone(),
        };
        let decomp_ms = t1.elapsed().as_secs_f64() * 1000.0;

        println!(
            "{:<28} {:>10?} {:>8} {:>12} {:>10.2} {:>10.2}  {}",
            name,
            format,
            raw.len() / 1024,
            decompressed.len() / 1024,
            read_ms,
            decomp_ms,
            version_line(&decompressed)
        );

        total_read_ms += read_ms;
        total_decomp_ms += decomp_ms;
        total_raw += raw.len() as u64;
        total_decomp += decompressed.len() as u64;
    }

    println!();
    println!(
        "TOTAL raw={}KB decomp={}KB read={:.2}ms decomp={:.2}ms",
        total_raw / 1024,
        total_decomp / 1024,
        total_read_ms,
        total_decomp_ms
    );
}
