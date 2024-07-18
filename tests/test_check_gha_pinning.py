import unittest

from check_gha_pinning import _build_github_url


class TestGHAPinning(unittest.TestCase):
    def test_build_github_url(self):
        data = [
            ("actions/checkout", "https://github.com/actions/checkout"),
            ("actions/checkout@v4", "https://github.com/actions/checkout"),
            ("actions/checkout@aaf4c61ddcc5e8a2dabede0f3b482cd9aea9434d", "https://github.com/actions/checkout"),
            ("actions/something/else@v4", "https://github.com/actions/something"),
        ]
        for action, expected in data:
            self.assertEqual(_build_github_url(action), expected)
        with self.assertRaises(AttributeError):
            _build_github_url("invalid")


if __name__ == "__main__":
    unittest.main()
