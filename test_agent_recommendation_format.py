import unittest
from unittest.mock import patch

from agent_core import process_turn


class AgentRecommendationFormatTests(unittest.TestCase):
    @patch("agent_core.search_schemes")
    def test_recommendation_includes_source_and_reason_details(self, mock_search):
        mock_search.return_value = [
            {
                "scheme_id": "pmsby",
                "name_hi": "प्रधानमंत्री सुरक्षा बीमा योजना (PMSBY)",
                "summary_hi": "₹2 लाख तक दुर्घटना बीमा",
                "apply_hi": "बैंक के माध्यम से आवेदन करें",
                "documents_hi": ["आधार", "बैंक खाता"],
                "score": 0.9,
                "source_url": "https://jansuraksha.gov.in/",
                "apply_link": "https://jansuraksha.gov.in/",
                "freshness_note_hi": "डेटा अपेक्षाकृत नया है",
                "is_stale": False,
                "eligibility_points_hi": ["18-70 वर्ष आयु आवश्यक"],
            }
        ]

        memory = {
            "stage": "READY",
            "goal": "बीमा योजना चाहिए",
            "profile": {
                "state": "Bihar",
                "age": 25,
                "annual_income": 250000,
                "category": "OBC",
                "is_student": False,
                "gender": "male",
            },
            "pending_confirm": None,
            "expected_field": None,
            "last_results": None,
            "selected_scheme": None,
        }

        text, mem = process_turn("कोई योजना बताइए", "Hindi", memory)
        self.assertEqual(mem["stage"], "RECOMMEND")
        self.assertIn("आधिकारिक स्रोत", text)
        self.assertIn("कारण", text)


if __name__ == "__main__":
    unittest.main()
