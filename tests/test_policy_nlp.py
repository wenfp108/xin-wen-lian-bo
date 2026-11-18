"""policy_nlp v2 的核心回归测试（标准库 unittest，无需 pytest）。"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import policy_nlp as nlp


def article(title, body="", index=1, duration="01:00"):
    return {
        "index": index,
        "title": title,
        "content": body,
        "duration_str": duration,
        "duration_sec": nlp.parse_duration(duration),
    }


class TestMatching(unittest.TestCase):
    def test_longest_match_does_not_double_count(self):
        terms = [t for t, _ in nlp.find_hits("新能源汽车销量创新高")]
        self.assertIn("新能源汽车", terms)
        self.assertNotIn("汽车", terms)
        self.assertNotIn("能源", terms)

    def test_one_term_can_map_to_multiple_sectors(self):
        result = nlp.analyze_article(article("新能源汽车下乡"))
        self.assertIn("新能源", result["sectors"])
        self.assertIn("汽车", result["sectors"])

    def test_negation_goes_to_negative_bucket(self):
        result = nlp.analyze_article(article("防范化解房地产风险"))
        self.assertNotIn("房地产", result["sectors"])
        self.assertGreaterEqual(result["negative_sectors"].get("房地产", 0), 1)

    def test_metaphor_is_not_counted(self):
        # “农业的芯片”指的是种质资源，不是半导体
        result = nlp.analyze_article(article("打通农业的芯片", "依托种质资源，做强农业的芯片。"))
        self.assertNotIn("半导体", result["sectors"])

    def test_title_weight_is_higher_than_body(self):
        title_only = nlp.analyze_article(article("光伏装机创新高"))
        body_only = nlp.analyze_article(article("今日要闻", "光伏装机创新高"))
        self.assertGreater(title_only["sectors"]["新能源"], body_only["sectors"]["新能源"])


class TestDayAggregation(unittest.TestCase):
    TEXT = (
        "## 新闻摘要\n\n1.测试\n\n"
        "### 光伏装机创新高\n\n**视频时长:** 02:00\n\n<p>新能源装机持续增长。</p>\n\n"
        "### 消费市场回暖\n\n**视频时长:** 01:00\n\n<p>假期消费升温。</p>\n\n"
        "### 防范房地产风险\n\n**视频时长:** 01:00\n\n<p>坚持防范化解房地产风险。</p>\n"
    )

    def test_attention_is_bounded_and_denominator_is_article_count(self):
        result = nlp.analyze_text(self.TEXT, "20260101")
        self.assertEqual(result["news_count"], 3)
        self.assertEqual(result["sector_attention"]["新能源"], round(1 / 3, 4))
        self.assertAlmostEqual(result["sector_attention"]["消费"], round(1 / 3, 4))
        self.assertNotIn("房地产", result["sector_attention"])
        for value in result["sector_attention"].values():
            self.assertGreaterEqual(value, 0)
            self.assertLessEqual(value, 1)

    def test_schema_is_backward_compatible(self):
        result = nlp.analyze_text(self.TEXT, "20260101")
        for key in ("date", "news_count", "sector_scores", "top_keywords", "items"):
            self.assertIn(key, result)
        for item in result["items"]:
            for key in ("index", "title", "duration", "sectors", "signal_score", "duration_score", "total_score"):
                self.assertIn(key, item)


class TestRollingStats(unittest.TestCase):
    def test_zscore_detects_spike(self):
        history = [
            {"date": f"2026010{i}", "attention": {"科技": 0.10}, "z": {}}
            for i in range(1, 10)
        ]
        zs, emas = nlp.rolling_stats(history, {"科技": 0.60})
        self.assertGreaterEqual(zs["科技"], 3)
        self.assertGreater(emas["科技"], 0.10)

    def test_zscore_is_none_without_history(self):
        zs, _ = nlp.rolling_stats([], {"科技": 0.5})
        self.assertIsNone(zs["科技"])

    def test_event_detection(self):
        history = [
            {"date": f"2026010{i}", "attention": {"基建": 0.10}, "z": {"基建": 1.6}}
            for i in range(1, 9)
        ]
        events = nlp.detect_events({"基建": 3.2}, history, {"基建": 0.4})
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["level"], "strong")

        watch = nlp.detect_events({"基建": 2.2}, history, {"基建": 0.4})
        self.assertEqual(watch[0]["level"], "watch")
        self.assertTrue(watch[0]["sustained"])

        # 单日尖峰 + 低注意力不应该报事件
        noisy = nlp.detect_events({"基建": 2.2}, [], {"基建": 0.05})
        self.assertEqual(noisy, [])


class TestKeywords(unittest.TestCase):
    def test_numbers_and_generic_words_are_filtered(self):
        words = [k for k, _ in nlp.extract_keywords("2026年 2026 发展 建设 光伏 产业链 光伏", 10)["tfidf"]]
        self.assertNotIn("2026", words)
        self.assertNotIn("发展", words)
        self.assertNotIn("建设", words)


if __name__ == "__main__":
    unittest.main(verbosity=2)
