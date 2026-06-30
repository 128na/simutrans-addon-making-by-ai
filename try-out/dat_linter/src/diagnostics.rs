use std::fmt;

/// 宣言順 = 重大度の高い順。Ord導出により `severity <= level` で
/// 「指定levelでも表示すべきか」を判定できる（Error=0が常に表示される）。
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord)]
pub enum Severity {
    /// pak化に失敗する、またはゲーム内で正常に表示されない
    Error,
    /// 非推奨な項目、動作はするが設定が推奨される項目
    Warning,
    /// 正常な項目の簡易な出力
    Info,
    /// 詳細な監査ログ
    Debug,
}

impl Severity {
    /// CLIの -v 指定回数からこのlevelへの変換
    pub fn from_verbosity(count: u8) -> Self {
        match count {
            0 => Severity::Warning,
            1 => Severity::Info,
            _ => Severity::Debug,
        }
    }
}

impl fmt::Display for Severity {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Severity::Error => write!(f, "error"),
            Severity::Warning => write!(f, "warn"),
            Severity::Info => write!(f, "info"),
            Severity::Debug => write!(f, "debug"),
        }
    }
}

pub struct Diagnostic {
    pub severity: Severity,
    pub code: &'static str,
    pub message: String,
}

impl Diagnostic {
    pub fn error(code: &'static str, message: impl Into<String>) -> Self {
        Diagnostic {
            severity: Severity::Error,
            code,
            message: message.into(),
        }
    }

    pub fn warning(code: &'static str, message: impl Into<String>) -> Self {
        Diagnostic {
            severity: Severity::Warning,
            code,
            message: message.into(),
        }
    }

    pub fn info(code: &'static str, message: impl Into<String>) -> Self {
        Diagnostic {
            severity: Severity::Info,
            code,
            message: message.into(),
        }
    }

    pub fn debug(code: &'static str, message: impl Into<String>) -> Self {
        Diagnostic {
            severity: Severity::Debug,
            code,
            message: message.into(),
        }
    }
}

impl fmt::Display for Diagnostic {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "[{}] {}: {}", self.severity, self.code, self.message)
    }
}
