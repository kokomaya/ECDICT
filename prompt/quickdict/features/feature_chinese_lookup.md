# Feature: 中文查词对话框（Chinese → English Lookup）

## 1. 概述

当前 QuickDict 仅支持通过屏幕取词识别英文单词后查询翻译。本功能增加一个**输入对话框**，用户通过快捷键唤出后，输入中文词语，反查对应的英文单词及详细释义。

---

## 2. 用户场景

- 用户想表达某个中文概念但不知道对应的英文单词
- 用户记得中文意思但想确认英文拼写、用法
- 用户想浏览某个中文含义对应的多个英文近义词

---

## 3. 交互设计

### 3.1 唤出方式

| 方式 | 描述 |
|------|------|
| 快捷键 | 取词模式下按 `Ctrl+F` 或独立快捷键（如 `Ctrl+Alt+F`）唤出对话框 |
| 托盘菜单 | 右键托盘 → 「中文查词」 |

### 3.2 对话框 UI

```
┌─────────────────────────────────────────────┐
│  🔍 中文查词                          [×]   │
├─────────────────────────────────────────────┤
│  ┌─────────────────────────────────┐  [查询] │
│  │ 感知                            │         │
│  └─────────────────────────────────┘         │
├─────────────────────────────────────────────┤
│  匹配结果 (3)                                │
│                                              │
│  1. perceive  /pəˈsiːv/            ★★★☆☆   │
│     vt. 察觉，感觉；理解；认知              │
│                                              │
│  2. perception  /pəˈsɛpʃən/        ★★★☆☆   │
│     n. 感知；感觉；认识；看法               │
│                                              │
│  3. sense  /sɛns/                   ★★★★★   │
│     n. 感觉，感知；意义 vt. 感觉到          │
│                                              │
└─────────────────────────────────────────────┘
```

### 3.3 交互流程

1. 用户按快捷键 → 弹出中文查词对话框（居中或跟随光标）
2. 输入框自动获得焦点，用户输入中文关键词
3. 按 Enter 或点击「查询」按钮触发搜索
4. 结果列表展示匹配的英文词条（按相关度/词频排序）
5. 点击某个结果条目 → 展开完整释义（复用现有 popup 格式）
6. 按 Esc 或点击关闭按钮 → 关闭对话框

### 3.4 输入增强（可选）

- 支持实时搜索（输入后 300ms 防抖自动查询）
- 输入框保留上次查询内容，打开时自动选中便于覆盖
- 支持按 ↑↓ 键在结果列表中导航

---

## 4. 查询策略

### 4.1 数据库字段

利用 ECDICT `stardict` 表的 `translation` 字段进行反向查询。该字段存储中文释义文本（如 `"vt. 察觉，感觉；理解；认知"`）。

### 4.2 查询逻辑

```
用户输入: "感知"
    ↓
1. LIKE 匹配: SELECT * FROM stardict WHERE translation LIKE '%感知%'
    ↓
2. 结果排序:
   - 优先级 1: translation 中以输入词开头的条目（如 "感知；…"）
   - 优先级 2: collins 星级高者优先
   - 优先级 3: BNC/FRQ 词频高者（数值小 = 频率高）优先
   - 优先级 4: 单词长度短者优先（更基本的词）
    ↓
3. 限制返回: 最多返回 20 条结果
```

### 4.3 性能优化

- **FTS 全文索引（推荐）**：为 `translation` 字段建立 FTS5 虚拟表，支持高效中文子串匹配
- **退化方案**：若不建 FTS，直接 `LIKE '%keyword%'` 查询（对 77 万条数据可能需 200-500ms，仍可接受）
- **结果缓存**：对相同输入使用 LRU 缓存避免重复查询

### 4.4 索引方案（可选增强）

```sql
-- 方案 A: FTS5 全文搜索（推荐）
CREATE VIRTUAL TABLE IF NOT EXISTS stardict_fts USING fts5(
    word,
    translation,
    content='stardict',
    content_rowid='id'
);

-- 方案 B: 若仅需简单 LIKE，可不加额外索引（SQLite LIKE 无法利用索引）
```

---

## 5. 模块设计

### 5.1 新增文件

| 文件 | 职责 |
|------|------|
| `quickdict/_chinese_lookup.py` | 中文反查逻辑：SQL 查询 + 结果排序 |
| `quickdict/lookup_dialog.py` | 查词对话框 UI 组件（QDialog） |

### 5.2 修改文件

| 文件 | 变更 |
|------|------|
| `quickdict/dict_engine.py` | 新增 `reverse_lookup(chinese: str) -> list[dict]` 方法 |
| `quickdict/hotkey.py` | 新增查词对话框快捷键监听 |
| `quickdict/app.py` | 托盘菜单添加「中文查词」选项，新增信号 `sig_open_lookup` |
| `quickdict/main.py` | 连接信号，管理 `LookupDialog` 生命周期 |
| `quickdict/build_db.py` | （可选）构建 FTS 索引步骤 |

### 5.3 类设计

```python
# _chinese_lookup.py
class ChineseLookup:
    """中文 → 英文反查引擎。"""

    def __init__(self, db_path: str): ...

    def search(self, keyword: str, limit: int = 20) -> list[dict]:
        """
        根据中文关键词搜索匹配的英文词条。
        返回按相关度排序的词条列表，每个 dict 包含:
        word, phonetic, translation, collins, bnc, frq, tag
        """
        ...

# lookup_dialog.py
class LookupDialog(QDialog):
    """中文查词输入对话框。"""

    sig_detail_requested = pyqtSignal(str)  # 用户点击某词条，请求完整释义

    def __init__(self, parent=None): ...
    def show_results(self, results: list[dict]): ...
    def clear(self): ...
```

### 5.4 信号流

```
用户按快捷键 (Ctrl+F / Ctrl+Alt+F)
    ↓
hotkey.py → sig_open_lookup 信号
    ↓
main.py 接收信号 → 显示 LookupDialog
    ↓
用户输入中文 + 按 Enter
    ↓
LookupDialog → DictEngine.reverse_lookup(keyword)
    ↓
_chinese_lookup.py 执行 SQL 查询 + 排序
    ↓
LookupDialog.show_results() 展示结果列表
    ↓
用户点击某条目 → sig_detail_requested → 展示完整弹窗
```

---

## 6. 样式

- 对话框风格与现有 popup 保持一致（圆角、阴影、相同配色）
- 结果列表每条紧凑展示：单词 + 音标 + 星级 + 一行中文释义
- 选中/悬停高亮效果
- 支持深浅色主题切换（复用现有 `popup.qss` 变量体系）

---

## 7. 边界情况

| 情况 | 处理 |
|------|------|
| 输入为空 | 不执行查询，提示"请输入中文关键词" |
| 无匹配结果 | 列表区显示"未找到匹配结果" |
| 输入含英文 | 正常执行 LIKE 查询（translation 字段可能含英文标注） |
| 输入过短（单字） | 正常查询但结果可能较多，依赖 LIMIT 截断 |
| 查询耗时长 | 在工作线程中执行，UI 显示加载动画 |

---

## 8. 后续扩展（不在本期）

- 支持拼音输入模糊匹配
- 查词历史记录与收藏
- 结果支持复制单词/释义到剪贴板
- 双向查词：同一对话框自动识别输入语言（中/英），切换查询方向
