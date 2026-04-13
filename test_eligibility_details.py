import unittest

from tools.eligibility import check_eligibility


class EligibilityDetailsTests(unittest.TestCase):
    def test_reason_blocks_and_missing_fields(self):
        profile = {"state": "Bihar", "age": 19, "annual_income": 200000}
        scheme_data = {
            "source_url": "https://jansuraksha.gov.in/",
            "eligibility_points_hi": ["Eligible age group 18-70"],
        }
        out = check_eligibility("pmsby", profile, scheme_data=scheme_data)
        self.assertIn(out["status"], ["eligible", "unknown", "not_eligible"])
        self.assertIn("reason_blocks", out)
        self.assertGreaterEqual(len(out["reason_blocks"]), 1)
        self.assertEqual(out["external_eligibility_points"], ["Eligible age group 18-70"])


if __name__ == "__main__":
    unittest.main()
