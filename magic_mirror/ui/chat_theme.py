"""聊天对话框主题 — 色彩系统与 QSS 样式表。

职责单一：只定义 ChatDialog 的视觉外观（色值、QSS），
不涉及 UI 构建或业务逻辑。
"""

# ------------------------------------------------------------------
# 色彩系统（Claude Code 风格：Catppuccin Mocha 基调）
# ------------------------------------------------------------------

BG_WINDOW = "#181825"
BG_CHAT = "#1e1e2e"
BG_INPUT = "#242438"
BG_SIDEBAR = "#1a1a2e"
BG_HUMAN = "#2a2a3e"
BG_AI = "transparent"
BG_SYSTEM = "#2c1a1a"

TEXT = "#cdd6f4"
TEXT_DIM = "#6c7086"
TEXT_HUMAN = "#89b4fa"
TEXT_AI = "#a6e3a1"
TEXT_ERR = "#f38ba8"

ACCENT = "#cba6f7"
ACCENT_DIM = "#45475a"
BORDER = "#313244"

# ------------------------------------------------------------------
# QSS 样式表
# ------------------------------------------------------------------

CHAT_DIALOG_QSS = f"""
QDialog {{
    background: {BG_WINDOW};
    color: {TEXT};
}}
QLabel {{
    background: transparent;
    color: {TEXT_DIM};
}}

/* ── 顶部栏 ── */
QWidget#topBar {{
    background: {BG_WINDOW};
    border-bottom: 1px solid {BORDER};
}}
QLabel#logoLabel {{
    color: {ACCENT};
    font-size: 15px;
    font-weight: 700;
    letter-spacing: 1px;
}}
QLabel#tokenBadge {{
    color: {TEXT_DIM};
    font-size: 10px;
    background: {ACCENT_DIM};
    border-radius: 9px;
    padding: 2px 8px;
}}
QComboBox {{
    background: {BG_INPUT};
    color: {TEXT};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 4px 10px;
    font-size: 11px;
}}
QComboBox:hover {{ border-color: {ACCENT}; }}
QComboBox::drop-down {{ border: none; width: 20px; }}
QComboBox QAbstractItemView {{
    background: {BG_INPUT};
    color: {TEXT};
    border: 1px solid {BORDER};
    selection-background-color: {ACCENT_DIM};
    outline: 0;
}}

/* ── 对话区 ── */
QTextEdit#chatView {{
    background: {BG_CHAT};
    border: none;
    padding: 0;
    selection-background-color: rgba(203,166,247,0.25);
}}

/* ── 输入区 ── */
QPlainTextEdit#inputBox {{
    background: {BG_INPUT};
    color: {TEXT};
    border: 1px solid {ACCENT_DIM};
    border-radius: 12px;
    padding: 10px 14px;
    font-size: 13px;
    selection-background-color: rgba(203,166,247,0.3);
}}
QPlainTextEdit#inputBox:focus {{ border-color: {ACCENT}; }}

QPushButton#sendBtn {{
    background: {ACCENT};
    color: {BG_WINDOW};
    border: none;
    border-radius: 10px;
    padding: 8px 22px;
    font-size: 13px;
    font-weight: 700;
}}
QPushButton#sendBtn:hover {{ background: #b4befe; }}
QPushButton#sendBtn:disabled {{ background: {ACCENT_DIM}; color: {TEXT_DIM}; }}

QPushButton#clearBtn {{
    background: transparent;
    color: {TEXT_DIM};
    border: 1px solid {BORDER};
    border-radius: 10px;
    padding: 6px 14px;
    font-size: 12px;
}}
QPushButton#clearBtn:hover {{ color: {TEXT}; border-color: {TEXT_DIM}; }}

/* ── 侧栏 ── */
QPlainTextEdit#ctxEdit {{
    background: {BG_SIDEBAR};
    color: {TEXT_DIM};
    border: none;
    padding: 8px;
    font-size: 11px;
    border-radius: 6px;
}}

/* ── 滚动条 ── */
QScrollBar:vertical {{
    background: transparent;
    width: 6px;
}}
QScrollBar::handle:vertical {{
    background: {ACCENT_DIM};
    border-radius: 3px;
    min-height: 30px;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: none; }}
"""
