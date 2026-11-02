import unittest
from types import SimpleNamespace

from bsk.errors import ConfigurationError
from bsk.providers.router import ProviderRouter


class FakeProvider:
    def __init__(self, name, value):
        self.name = name
        self.value = value

    def generate_json(self, system, prompt, temperature=0.4):
        return {"provider": self.name, "value": self.value}


class RouterTests(unittest.TestCase):
    def setUp(self):
        self.config = SimpleNamespace(writer_provider="gemini", max_provider_attempts=1, confirm_free_only=True)

    def test_router_uses_one_provider_sequentially(self):
        router = ProviderRouter(self.config, {
            "gemini": FakeProvider("gemini", "draft"),
            "groq": FakeProvider("groq", "critique"),
        })
        name, payload = router.generate_json("system", "prompt")
        self.assertEqual(name, "gemini")
        self.assertEqual(payload["value"], "draft")

    def test_independent_critic_must_be_different_provider(self):
        router = ProviderRouter(self.config, {"gemini": FakeProvider("gemini", "draft")})
        with self.assertRaises(ConfigurationError):
            router.require_independent_critic("gemini")

    def test_exclusion_selects_second_provider(self):
        router = ProviderRouter(self.config, {
            "gemini": FakeProvider("gemini", "draft"),
            "groq": FakeProvider("groq", "critic"),
        })
        name, payload = router.generate_json("system", "prompt", exclude={"gemini"})
        self.assertEqual(name, "groq")
        self.assertEqual(payload["value"], "critic")


if __name__ == "__main__":
    unittest.main()
