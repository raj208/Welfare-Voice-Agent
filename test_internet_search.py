import unittest
from urllib.parse import urlparse
from unittest.mock import patch

from tools.internet_search import fetch_scheme_details_from_internet, enrich_scheme_results


class _Resp:
    def __init__(self, text, url):
        self.text = text
        self.url = url

    def raise_for_status(self):
        return None


class InternetSearchTests(unittest.TestCase):
    @patch("tools.internet_search.requests.get")
    def test_fetch_scheme_details_success(self, mock_get):
        html = """
        <html><body>
        <h1>Eligibility Criteria</h1>
        <p>Eligibility: Applicants must be students and satisfy age criteria.</p>
        <p>Benefits include scholarship amount and fee support.</p>
        <p>Required documents: Aadhaar, marksheet, bank account proof.</p>
        <p>Apply online through the official portal.</p>
        </body></html>
        """
        mock_get.return_value = _Resp(html, "https://scholarships.gov.in/")

        out = fetch_scheme_details_from_internet("nsp", "NSP")
        self.assertEqual(out["fetch_status"], "ok")
        self.assertEqual(urlparse(out["source_url"]).netloc, "scholarships.gov.in")
        self.assertGreaterEqual(len(out["eligibility_points_hi"]), 1)

    @patch("tools.internet_search.requests.get", side_effect=Exception("network down"))
    def test_fetch_scheme_details_failure(self, _):
        out = fetch_scheme_details_from_internet("pmjay", "PMJAY")
        self.assertEqual(out["fetch_status"], "failed")
        self.assertIn("official", out["source_type"])

    def test_enrich_scheme_results_fallback_shape(self):
        local = [{"scheme_id": "pmsby", "name_hi": "PMSBY", "summary_hi": "s", "score": 0.9, "documents_hi": []}]
        out = enrich_scheme_results(local, use_internet=False)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["scheme_id"], "pmsby")


if __name__ == "__main__":
    unittest.main()
