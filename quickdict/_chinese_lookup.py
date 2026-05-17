"""
_chinese_lookup.py — 中文 → 英文反查引擎。

职责单一：根据中文关键词在 translation 字段中搜索匹配的英文词条，
按相关度排序后返回结果列表。
"""
import sqlite3
from functools import lru_cache


class ChineseLookup:
    """中文 → 英文反查引擎。"""

    def __init__(self, db_path: str, *, check_same_thread: bool = True):
        self._conn = sqlite3.connect(db_path, check_same_thread=check_same_thread)
        self._conn.execute("PRAGMA query_only=ON;")
        self._conn.row_factory = sqlite3.Row

    def search(self, keyword: str, limit: int = 20) -> list[dict]:
        """
        根据中文关键词搜索匹配的英文词条。

        返回按相关度排序的词条列表，每个 dict 包含:
        word, phonetic, translation, definition, collins, bnc, frq, tag, exchange
        """
        keyword = keyword.strip()
        if not keyword:
            return []
        return self._search_cached(keyword, limit)

    @lru_cache(maxsize=200)
    def _search_cached(self, keyword: str, limit: int) -> list[dict]:
        """带缓存的搜索实现。"""
        # 使用参数化查询防止 SQL 注入
        pattern = f"%{keyword}%"
        cursor = self._conn.execute(
            """
            SELECT word, phonetic, translation, definition,
                   collins, oxford, bnc, frq, tag, exchange
            FROM stardict
            WHERE translation LIKE ?
            ORDER BY
                -- 优先级 1: collins 星级高者优先（负数排序）
                -(CASE WHEN collins IS NULL THEN 0 ELSE collins END),
                -- 优先级 2: BNC 词频高者（数值小 = 频率高）优先
                CASE WHEN bnc IS NULL OR bnc = 0 THEN 999999 ELSE bnc END,
                -- 优先级 3: 单词长度短者优先（更基本的词汇）
                LENGTH(word)
            LIMIT ?
            """,
            (pattern, limit),
        )
        results = []
        for row in cursor:
            results.append({
                "word": row["word"],
                "phonetic": row["phonetic"] or "",
                "translation": row["translation"] or "",
                "definition": row["definition"] or "",
                "collins": row["collins"] or 0,
                "oxford": row["oxford"] or 0,
                "bnc": row["bnc"] or 0,
                "frq": row["frq"] or 0,
                "tag": row["tag"] or "",
                "exchange": row["exchange"] or "",
            })
        return results

    def close(self):
        """关闭数据库连接。"""
        if self._conn:
            self._conn.close()
            self._conn = None

    def __del__(self):
        self.close()
