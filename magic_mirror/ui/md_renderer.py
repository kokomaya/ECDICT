"""Markdown → HTML 渲染器 — 将 LLM 响应转为富文本 HTML。

职责单一：只负责 Markdown 文本到 styled HTML 的转换，
不涉及 UI 组件或网络调用。
"""

from __future__ import annotations

import markdown
from markdown.extensions.codehilite import CodeHiliteExtension
from markdown.extensions.fenced_code import FencedCodeExtension

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


def render_markdown(text: str) -> str:
    """将 Markdown 文本转换为带内联样式的 HTML 片段。"""
    _MD.reset()
    html_body = _MD.convert(text)
    return html_body
