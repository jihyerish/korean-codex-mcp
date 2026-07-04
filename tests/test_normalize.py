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
        self.assertEqual(result["items"][0]["document_key"], "001570")
        self.assertEqual(result["items"][0]["key_type"], "id")
        self.assertEqual(result["items"][0]["effective_date"], "2025-01-01")
        self.assertTrue(result["items"][0]["detail_url"].startswith("https://www.law.go.kr"))

    def test_administrative_rule_search_uses_id_parameter_with_serial_number(self) -> None:
        parsed = {
            "AdmRulSearch": {
                "totalCnt": "1",
                "admrul": {
                    "행정규칙명": "근로기준법 관련 지침",
                    "행정규칙일련번호": "2100000229722",
                    "행정규칙ID": "86745",
                },
            }
        }

        result = normalize_search_response(parsed, target="admrul", query="근로기준법", page=1, limit=10)

        self.assertEqual(result["items"][0]["document_key"], "2100000229722")
        self.assertEqual(result["items"][0]["key_type"], "id")

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

    def test_normalize_local_ordinance_articles(self) -> None:
        parsed = {
            "LawService": {
                "자치법규기본정보": {
                    "자치법규명": "서울특별시 송파구 규칙",
                    "지자체기관명": "서울특별시 송파구",
                },
                "조문": {
                    "조": {
                        "조문번호": "000100",
                        "조제목": "목적",
                        "조내용": "제1조(목적) 이 규칙은 필요한 사항을 정한다.",
                    }
                },
            }
        }

        result = normalize_detail_response(parsed, target="ordin")

        self.assertEqual(result["title"], "서울특별시 송파구 규칙")
        self.assertEqual(result["articles"][0]["article_number"], "제1조")
        self.assertIn("목적", result["articles"][0]["content"])

    def test_filter_articles_matches_compact_korean_terms(self) -> None:
        articles = [
            {
                "label": "제60조(연차 유급휴가)",
                "title": "연차 유급휴가",
                "content": "사용자는 근로자에게 유급휴가를 주어야 한다.",
            }
        ]

        result = filter_articles(articles, "연차유급휴가는 어떻게 계산해?", 1)

        self.assertEqual(result[0]["label"], "제60조(연차 유급휴가)")


if __name__ == "__main__":
    unittest.main()
