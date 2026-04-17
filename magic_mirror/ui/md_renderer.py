"""Markdown → HTML 渲染器 — 将 LLM 响应转为富文本 HTML。

职责单一：负责 Markdown 文本 → styled HTML 转换，
以及聊天消息级别的 HTML 组合。不涉及 UI 组件或网络调用。
"""

from __future__ import annotations

import html as html_mod

import markdown
from markdown.extensions.codehilite import CodeHiliteExtension

from magic_mirror.ui.chat_theme import (
    BG_AI,
    BG_HUMAN,
    BG_SYSTEM,
    TEXT_AI,
    TEXT_DIM,
    TEXT_ERR,
    TEXT_HUMAN,
)

# Pygments 代码高亮 — 暗色主题内联样式
_MD = markdown.Markdown(
    extensions=[
        "fenced_code",
        "tables",
        "sane_lists",
        CodeHiliteExtension(noclasses=True, pygments_style="monokai"),
    ],
)

# 代码块和整体富文本的 CSS（嵌入到每条消息中）
MESSAGE_CSS = """\
body {
    font-family: 'Microsoft YaHei', 'Segoe UI', sans-serif;
    font-size: 13px;
    line-height: 1.65;
    color: #e0e0e0;
    margin: 0;
    padding: 0;
}
p { margin: 4px 0; }
ul, ol { margin: 4px 0 4px 18px; padding: 0; }
li { margin: 2px 0; }
h1, h2, h3, h4 {
    color: #c9d1d9;
    margin: 8px 0 4px 0;
    font-weight: 600;
}
h1 { font-size: 17px; }
h2 { font-size: 15px; }
h3 { font-size: 14px; }
strong { color: #f0f0f0; }
em { color: #c4b5fd; }
a { color: #818cf8; text-decoration: none; }
code {
    background: #1e1e2e;
    color: #a5d6ff;
    padding: 1px 5px;
    border-radius: 4px;
    font-family: 'Cascadia Code', 'Consolas', monospace;
    font-size: 12px;
}
pre {
    background: #11111b;
    border: 1px solid #313244;
    border-radius: 8px;
    padding: 10px 14px;
    overflow-x: auto;
    margin: 6px 0;
}
pre code {
    background: transparent;
    padding: 0;
    font-size: 12px;
    line-height: 1.5;
}
table {
    border-collapse: collapse;
    margin: 6px 0;
}
th, td {
    border: 1px solid #313244;
    padding: 4px 10px;
    font-size: 12px;
}
th { background: #1e1e2e; color: #c9d1d9; }
td { background: #181825; }
blockquote {
    border-left: 3px solid #6366f1;
    margin: 6px 0;
    padding: 4px 12px;
    color: #9ca3af;
    background: #1e1e2e;
    border-radius: 0 6px 6px 0;
}
hr {
    border: none;
    border-top: 1px solid #313244;
    margin: 8px 0;
}
"""


import re as _re

# 预处理：在列表/代码块/标题前自动补空行（LLM 输出常缺少）
_BLOCK_START = _re.compile(
    r"(?<!\n\n)"           # 前面不是空行
    r"(?<=\n)"             # 前面是换行
    r"([ \t]*[-*+] |\d+\. |```|#{1,6} )",  # 列表/代码块/标题起始
)


def _ensure_blank_lines(text: str) -> str:
    """在 Markdown 块级元素前补空行，确保解析器识别。"""
    return _BLOCK_START.sub(r"\n\1", text)


def render_markdown(text: str) -> str:
    """将 Markdown 文本转换为带内联样式的 HTML 片段。"""
    _MD.reset()
    html_body = _MD.convert(_ensure_blank_lines(text))
    return html_body


# ------------------------------------------------------------------
# 消息级 HTML 组合
# ------------------------------------------------------------------

_MSG_TEMPLATE = """\
<div style="padding:10px 16px; margin:0; background:{bg}; border-bottom:1px solid #313244;">
  <div style="margin-bottom:3px;">
    <span style="color:{label_color}; font-weight:700; font-size:12px;">{icon} {label}</span>
  </div>
  <div style="color:#cdd6f4; font-size:13px; line-height:1.6;">
    {content}
  </div>
</div>
"""


def render_message(role: str, text: str) -> str:
    """将单条聊天消息（含角色）渲染为完整 HTML 片段。

    Parameters
    ----------
    role : "human" | "assistant" | "error"
    text : 消息原文（assistant 为 Markdown，其余为纯文本）
    """
    if role == "human":
        content = html_mod.escape(text).replace("\n", "<br>")
        return _MSG_TEMPLATE.format(
            bg=BG_HUMAN, label_color=TEXT_HUMAN,
            icon="❯", label="Human", content=content,
        )

    if role == "assistant":
        content = render_markdown(text) if text else f'<span style="color:{TEXT_DIM};">…</span>'
        return _MSG_TEMPLATE.format(
            bg=BG_AI, label_color=TEXT_AI,
            icon="✦", label="Assistant", content=content,
        )

    # error
    content = f'<span style="color:{TEXT_ERR}">{html_mod.escape(text)}</span>'
    return _MSG_TEMPLATE.format(
        bg=BG_SYSTEM, label_color=TEXT_ERR,
        icon="⚠", label="Error", content=content,
    )


def build_messages_html(
    messages: list[dict],
    *,
    streaming: bool = False,
) -> str:
    """将消息列表组合为完整的 HTML body（含 <style>）。

    Parameters
    ----------
    messages : [{"role": str, "text": str}, ...]
    streaming : 是否显示 "generating…" 指示
    """
    parts: list[str] = []
    for msg in messages:
        parts.append(render_message(msg["role"], msg["text"]))
    if streaming:
        parts.append(
            f'<div style="padding:2px 18px; color:{TEXT_DIM}; font-size:11px;">'
            "● generating…</div>"
        )
    return "".join(parts)
