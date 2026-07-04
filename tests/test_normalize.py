import unittest

from law_mcp.normalize import (
    filter_articles,
    normalize_detail_response,
    normalize_search_response,
)


class NormalizeTests(unittest.TestCase):
    def test_normalize_search_response(self) -> None:
        parsed = {
            "LawSearch": {
                "totalCnt": "1",
                "law": {
                    "법령명한글": "근로기준법",
                    "법령일련번호": "12345",
                    "법령ID": "001570",
                    "소관부처명": "고용노동부",
                    "시행일자": "20250101",
                    "법령상세링크": "/DRF/lawService.do?target=eflaw&MST=12345",
                },
            }
        }

        result = normalize_search_response(parsed, target="eflaw", query="근로기준법", page=1, limit=10)

        self.assertEqual(result["total_count"], 1)
        self.assertEqual(result["items"][0]["title"], "근로기준법")
        self.assertEqual(result["items"][0]["document_key"], "12345")
        self.assertEqual(result["items"][0]["effective_date"], "2025-01-01")
        self.assertTrue(result["items"][0]["detail_url"].startswith("https://www.law.go.kr"))

    def test_normalize_detail_response_extracts_articles(self) -> None:
        parsed = {
            "법령": {
                "기본정보": {
                    "법령명_한글": "근로기준법",
                    "소관부처": "고용노동부",
                },
                "조문": {
                    "조문단위": [
                        {
                            "조문번호": "60",
                            "조문제목": "연차 유급휴가",
                            "조문내용": "제60조(연차 유급휴가)",
                            "항": {"항내용": "사용자는 근로자에게 유급휴가를 주어야 한다."},
                        }
                    ]
                },
            }
        }

        result = normalize_detail_response(parsed, target="eflaw")
        articles = filter_articles(result["articles"], "유급휴가", 3)

        self.assertEqual(result["title"], "근로기준법")
        self.assertEqual(articles[0]["article_number"], "제60조")
        self.assertIn("유급휴가", articles[0]["content"])


if __name__ == "__main__":
    unittest.main()

