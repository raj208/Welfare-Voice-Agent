import unittest
from unittest.mock import patch

from tools import retriever


class HybridRetrieverTests(unittest.TestCase):
    @patch("tools.retriever._semantic_search", return_value=[])
    @patch("tools.retriever._lexical_search")
    @patch("tools.internet_search.enrich_scheme_results")
    def test_hybrid_search_uses_lexical_and_enrichment(self, mock_enrich, mock_lexical, _):
        mock_lexical.return_value = [
            {
                "scheme_id": "pmsby",
                "name_hi": "PMSBY",
                "summary_hi": "बीमा",
                "apply_hi": "bank",
                "documents_hi": ["आधार"],
                "score": 0.7,
            }
        ]
        mock_enrich.return_value = [
            {
                "scheme_id": "pmsby",
                "name_hi": "PMSBY",
                "summary_hi": "बीमा",
                "apply_hi": "bank",
                "documents_hi": ["आधार"],
                "score": 0.7,
                "hybrid_score": 0.82,
                "source_confidence": 0.85,
            }
        ]

        out = retriever.search_schemes("बीमा योजना", top_k=1, use_internet=True)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["scheme_id"], "pmsby")
        self.assertAlmostEqual(out[0]["hybrid_score"], 0.82)


if __name__ == "__main__":
    unittest.main()
