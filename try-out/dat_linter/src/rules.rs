use crate::diagnostics::Diagnostic;
use crate::parser::DatFile;
use std::path::Path;

// type/waytype の既知一覧は makeobj の動作をミラーしている。
// type: simutrans/src/simutrans/descriptor/writer/building_writer.cc write_obj()
// waytype: simutrans/src/simutrans/descriptor/writer/get_waytype.cc
const KNOWN_TYPES: &[&str] = &[
    "res", "com", "ind", "cur", "mon", "tow", "hq", "habour", "harbour", "dock", "fac", "stop",
    "extension", "depot", "any", "",
];
const OBSOLETE_TYPES: &[&str] = &[
    "station",
    "railstop",
    "monorailstop",
    "busstop",
    "carstop",
    "airport",
    "wharf",
    "hall",
    "post",
    "shed",
];
const TYPES_REQUIRING_WAYTYPE: &[&str] = &["stop", "depot"];
const KNOWN_WAYTYPES: &[&str] = &[
    "none",
    "road",
    "track",
    "electrified_track",
    "maglev_track",
    "monorail_track",
    "narrowgauge_track",
    "water",
    "air",
    "schiene_tram",
    "tram_track",
    "power",
    "decoration",
];

pub fn check_building(dat: &DatFile, dat_dir: &Path) -> Vec<Diagnostic> {
    let mut diags = Vec::new();

    diags.push(Diagnostic::debug(
        "parsed-pairs",
        format!("{} 個のkey=valueを読み込み", dat.pairs.len()),
    ));

    let type_name = dat.get("type").unwrap_or("").to_ascii_lowercase();
    let waytype = dat.get("waytype").unwrap_or("").to_ascii_lowercase();
    diags.push(Diagnostic::debug(
        "raw-type-waytype",
        format!("type=\"{type_name}\" waytype=\"{waytype}\""),
    ));

    check_type_and_waytype(&type_name, &waytype, &mut diags);

    if dat.get("extension_building").is_some() {
        diags.push(Diagnostic::error(
            "obsolete-keyword",
            "extension_building は obsolete です。type=stop/extension と waytype を使ってください",
        ));
    }

    let (size_x, size_y, layouts) = check_dims(dat, &mut diags);

    check_cursor_icon(dat, dat_dir, &mut diags);

    check_tile_images(dat, dat_dir, size_x, size_y, layouts, &mut diags);

    diags
}

fn check_type_and_waytype(type_name: &str, waytype: &str, diags: &mut Vec<Diagnostic>) {
    if OBSOLETE_TYPES.contains(&type_name) {
        diags.push(Diagnostic::error(
            "obsolete-type",
            format!(
                "type={type_name} は obsolete です。stop/extension と waytype を使ってください"
            ),
        ));
        return;
    }
    if !KNOWN_TYPES.contains(&type_name) {
        diags.push(Diagnostic::error(
            "unknown-type",
            format!("type={type_name} は makeobj が認識できない値です（FATAL ERRORになります）"),
        ));
        return;
    }

    if TYPES_REQUIRING_WAYTYPE.contains(&type_name) {
        if waytype.is_empty() {
            diags.push(Diagnostic::error(
                "missing-waytype",
                format!("type={type_name} では waytype が必須です（未指定だとmakeobjがFATAL ERRORになります）"),
            ));
        } else if !KNOWN_WAYTYPES.contains(&waytype) {
            diags.push(Diagnostic::error(
                "unknown-waytype",
                format!("waytype={waytype} は不正な値です（FATAL ERRORになります）"),
            ));
        } else {
            diags.push(Diagnostic::info(
                "type-waytype-ok",
                format!("type={type_name} waytype={waytype}"),
            ));
        }
    } else if type_name == "extension" {
        if waytype.is_empty() {
            diags.push(Diagnostic::warning(
                "generic-extension",
                "type=extension で waytype 未指定は「全waytypeに適合する汎用拡張」として解釈されます。意図的でなければ waytype を指定してください",
            ));
        } else if !KNOWN_WAYTYPES.contains(&waytype) {
            diags.push(Diagnostic::error(
                "unknown-waytype",
                format!("waytype={waytype} は不正な値です（FATAL ERRORになります）"),
            ));
        } else {
            diags.push(Diagnostic::info(
                "type-waytype-ok",
                format!("type={type_name} waytype={waytype}"),
            ));
        }
    } else {
        diags.push(Diagnostic::info("type-waytype-ok", format!("type={type_name}")));
    }
}

fn check_dims(dat: &DatFile, diags: &mut Vec<Diagnostic>) -> (i64, i64, i64) {
    let ints = dat.get_ints("dims");
    let size_x = ints.first().copied().unwrap_or(1);
    let size_y = ints.get(1).copied().unwrap_or(1);
    let mut layouts = ints.get(2).copied().unwrap_or(0);
    if layouts == 0 {
        layouts = if size_x == size_y { 1 } else { 2 };
    }
    diags.push(Diagnostic::debug(
        "dims-resolved",
        format!("Dims={:?} -> size_x={size_x} size_y={size_y} layouts={layouts}", ints),
    ));

    if size_x * size_y == 0 {
        diags.push(Diagnostic::error(
            "zero-size",
            format!("Dims のサイズが0です (size_x={size_x}, size_y={size_y})"),
        ));
    } else {
        diags.push(Diagnostic::info(
            "dims-ok",
            format!("size={size_x}x{size_y} layouts={layouts}"),
        ));
    }

    (size_x, size_y, layouts)
}

fn check_cursor_icon(dat: &DatFile, dat_dir: &Path, diags: &mut Vec<Diagnostic>) {
    let cursor = dat.get("cursor").unwrap_or("");
    let icon = dat.get("icon").unwrap_or("");
    diags.push(Diagnostic::debug(
        "raw-cursor-icon",
        format!("cursor=\"{cursor}\" icon=\"{icon}\""),
    ));

    if cursor.is_empty() && icon.is_empty() {
        diags.push(Diagnostic::error(
            "missing-cursor-icon",
            "cursor と icon が両方とも未指定です。makeobjはエラーを出さずにビルドしますが、ゲーム内のビルドメニューに表示されません",
        ));
        return;
    }

    if !icon.is_empty() {
        check_image_ref(icon, dat_dir, "icon", true, diags);
    }
    if !cursor.is_empty() {
        check_image_ref(cursor, dat_dir, "cursor", true, diags);
    }
}

fn check_tile_images(
    dat: &DatFile,
    dat_dir: &Path,
    size_x: i64,
    size_y: i64,
    layouts: i64,
    diags: &mut Vec<Diagnostic>,
) {
    for l in 0..layouts {
        // building_writer.cc: 奇数レイアウトは縦横を入れ替えて走査する
        let (w, h) = if l % 2 == 1 {
            (size_y, size_x)
        } else {
            (size_x, size_y)
        };
        for y in 0..h {
            for x in 0..w {
                let front5 = format!("frontimage[{l}][{y}][{x}][0][0]");
                let back5 = format!("backimage[{l}][{y}][{x}][0][0]");
                let front6 = format!("frontimage[{l}][{y}][{x}][0][0][0]");
                let back6 = format!("backimage[{l}][{y}][{x}][0][0][0]");

                diags.push(Diagnostic::debug(
                    "tile-key-lookup",
                    format!("layout {l} tile ({x},{y}): {front5} / {back5} ({front6} / {back6} もfallback確認)"),
                ));

                let front = dat.get(&front5).or_else(|| dat.get(&front6));
                let back = dat.get(&back5).or_else(|| dat.get(&back6));

                if front.is_none() && back.is_none() {
                    diags.push(Diagnostic::error(
                        "missing-tile-image",
                        format!(
                            "layout {l} tile ({x},{y}) に front/backimage が1枚もありません（makeobjはエラーを出さず空画像のタイルを生成します）"
                        ),
                    ));
                } else {
                    diags.push(Diagnostic::info(
                        "tile-image-ok",
                        format!("layout {l} tile ({x},{y})"),
                    ));
                    if let Some(v) = front {
                        check_image_ref(v, dat_dir, &format!("frontimage[{l}][{y}][{x}]"), false, diags);
                    }
                    if let Some(v) = back {
                        check_image_ref(v, dat_dir, &format!("backimage[{l}][{y}][{x}]"), false, diags);
                    }
                }
            }
        }
    }

    // frontimage の高さ(h)は0のみ許可。h>0が定義されていないか確認する
    for key in dat.pairs.keys() {
        if let Some(rest) = key.strip_prefix("frontimage[") {
            let indices: Vec<&str> = rest.trim_end_matches(']').split("][").collect();
            // [l][y][x][h][phase] (+season)
            if let Some(h_str) = indices.get(3) {
                if h_str.parse::<i64>().unwrap_or(0) > 0 {
                    diags.push(Diagnostic::error(
                        "frontimage-height",
                        format!("{key} : frontimageの高さ(h)は0のみ有効です（makeobjはエラーログを出すだけで処理を継続します）"),
                    ));
                }
            }
        }
    }
}

fn check_image_ref(
    value: &str,
    dat_dir: &Path,
    context: &str,
    check_alpha_corner: bool,
    diags: &mut Vec<Diagnostic>,
) {
    let base = value.split(',').next().unwrap_or(value);
    let parts: Vec<&str> = base.split('.').collect();
    let filename = if parts.len() >= 2
        && parts[parts.len() - 1].parse::<i64>().is_ok()
        && parts[parts.len() - 2].parse::<i64>().is_ok()
    {
        parts[..parts.len() - 2].join(".")
    } else {
        base.to_string()
    };

    let path = dat_dir.join(&filename);
    diags.push(Diagnostic::debug(
        "image-ref-resolved",
        format!("{context}: \"{value}\" -> filename=\"{filename}\" path={}", path.display()),
    ));

    if !path.is_file() {
        diags.push(Diagnostic::error(
            "missing-image-file",
            format!("{context}: 参照画像 {filename} が見つかりません ({})", path.display()),
        ));
        return;
    }

    match image::open(&path) {
        Ok(img) => {
            let (w, h) = (img.width(), img.height());
            let mut ok = true;
            if w % 128 != 0 || h % 128 != 0 {
                ok = false;
                diags.push(Diagnostic::error(
                    "image-size-not-multiple-of-128",
                    format!("{context}: {filename} のサイズが {w}x{h} です。makeobj pak128 は128の倍数でないとエラーになります"),
                ));
            }
            if check_alpha_corner {
                let rgba = img.to_rgba8();
                if let Some(px) = rgba.get_pixel_checked(0, 0) {
                    if px[3] == 0 {
                        ok = false;
                        diags.push(Diagnostic::warning(
                            "transparent-corner-pixel",
                            format!("{context}: {filename} の左上(0,0)ピクセルが透過です。ゲームがアイコンを認識しない場合があります"),
                        ));
                    }
                }
            }
            if ok {
                diags.push(Diagnostic::info(
                    "image-ok",
                    format!("{context}: {filename} {w}x{h}"),
                ));
            }
        }
        Err(e) => {
            diags.push(Diagnostic::error(
                "unreadable-image",
                format!("{context}: {filename} を画像として読み込めません ({e})"),
            ));
        }
    }
}
