import unittest

from services import SERVICES, detect_service, get_service
from services.base import Service, matches_host


class DetectionTests(unittest.TestCase):
    def test_telemost_hosts(self):
        for url in (
            "https://telemost.yandex.ru/j/123",
            "https://telemost.yandex.com/j/123",
            "https://telemost.360.yandex.ru/j/123",
            "https://TELEMOST.360.YANDEX.RU:443/j/123?x=ktalk.ru",
        ):
            with self.subTest(url=url):
                self.assertEqual(detect_service(url), "telemost")

    def test_ktalk_hosts_and_subdomains(self):
        for url in (
            "https://ktalk.ru/event/1",
            "https://company.ktalk.ru/event/1",
            "https://COMPANY.KTALK.RU./event/1",
        ):
            with self.subTest(url=url):
                self.assertEqual(detect_service(url), "ktalk")

    def test_unknown_and_malformed_urls(self):
        for url in (
            "https://example.org/meet",
            "https://fakektalk.ru/event/1",
            "https://ktalk.ru.example.org/event/1",
            "https://ktalk.ru@example.org/event/1",
            "ftp://ktalk.ru/event/1",
            "ktalk.ru/event/1",
            "https://[invalid",
            "",
        ):
            with self.subTest(url=url):
                self.assertIsNone(detect_service(url))

    def test_registry_lookup(self):
        self.assertEqual(get_service("telemost").label, "Yandex Telemost")
        with self.assertRaises(KeyError):
            get_service("zoom")


class ServiceModelTests(unittest.TestCase):
    def test_suffix_patterns_do_not_match_the_bare_suffix(self):
        self.assertTrue(matches_host("a.example.com", ("*.example.com",)))
        self.assertFalse(matches_host("example.com", ("*.example.com",)))

    def test_exact_patterns_ignore_case_and_trailing_dot(self):
        self.assertTrue(matches_host("EXAMPLE.COM.", ("example.com",)))

    def test_service_requires_only_identity(self):
        service = Service(
            key="demo",
            label="Demo",
            hosts=("demo.example",),
            name_inputs=(("css selector", "input"),),
        )
        self.assertTrue(service.matches_host("demo.example"))
        self.assertFalse(service.matches_host("other.example"))
        self.assertEqual(service.join_buttons, ())

    def test_registry_entries_are_complete(self):
        for key, service in SERVICES.items():
            with self.subTest(service=key):
                self.assertEqual(service.key, key)
                self.assertTrue(service.label)
                self.assertTrue(service.hosts)
                self.assertTrue(service.name_inputs)
                self.assertTrue(service.join_buttons)

    def test_telemost_selectors_cover_the_embedded_join_frame(self):
        telemost = get_service("telemost")
        self.assertIn(
            "orb-textinput-input", " ".join(text for _, text in telemost.name_inputs)
        )
        self.assertIn(
            "enter-conference-button",
            " ".join(text for _, text in telemost.join_buttons),
        )
        self.assertTrue(telemost.frame_url_patterns)
        self.assertTrue(telemost.failure_markers)
        self.assertTrue(telemost.joined_markers)

    def test_ktalk_selectors_still_target_anonymous_authorization(self):
        ktalk = get_service("ktalk")
        self.assertIn("AnonymousAuthorization.Input", ktalk.name_inputs[0][1])
        self.assertIn("AnonymousAuthorization.Anonymous", ktalk.join_buttons[0][1])
        self.assertEqual(ktalk.frame_url_patterns, ())


if __name__ == "__main__":
    unittest.main()
