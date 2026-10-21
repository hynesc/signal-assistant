import unittest

from signal_bot.llm import parse_duckduckgo_results, sanitize_model_reply


class LLMTests(unittest.TestCase):
    def test_parse_duckduckgo_results_extracts_titles_and_snippets(self) -> None:
        html = """
        <div class="result__body">
          <a class="result__a" href="/l/?kh=-1">Example &amp; Result</a>
          <a class="result__snippet" href="/l/?kh=-1">A useful &lt;summary&gt;.</a>
        </div>
        """

        results = parse_duckduckgo_results(html)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].title, "Example & Result")
        self.assertEqual(results[0].snippet, "A useful <summary>.")

    def test_sanitize_model_reply_removes_reasoning_block(self) -> None:
        self.assertEqual(
            sanitize_model_reply("<think>private reasoning</think>\nfinal answer"),
            "final answer",
        )


if __name__ == "__main__":
    unittest.main()
