from django.core.cache import cache
from django.urls import reverse

from core.models import VisitorCounter, VisitorCountry
from core.testing import BaseTestCase
from dashboard.insights import STORAGE_CACHE_KEY, TOP_COUNTRIES, storage_usage, visitor_locations


class VisitorLocationTests(BaseTestCase):
    def test_rows_fold_extra_countries_and_unknown(self):
        VisitorCounter.objects.create(pk=1, total=200)
        codes = ["PH", "US", "CA", "JP", "SG", "AU", "GB", "DE", "FR", "IN"]
        for i, code in enumerate(codes):
            VisitorCountry.objects.create(code=code, visitors=20 - i)
        locations = visitor_locations()
        labels = [row.get("label", row["code"]) for row in locations["rows"]]
        self.assertEqual(labels[:3], ["PH", "US", "CA"])
        self.assertEqual(labels[TOP_COUNTRIES:], ["Other countries", "Unknown"])
        self.assertEqual(locations["rows"][TOP_COUNTRIES]["visitors"], 12 + 11)
        self.assertEqual(locations["rows"][-1]["visitors"], 200 - sum(20 - i for i in range(10)))
        self.assertEqual(max(row["width"] for row in locations["rows"]), 100)
        self.assertEqual(locations["countries"], 10)


class StorageUsageTests(BaseTestCase):
    def test_segments_add_up_to_disk(self):
        cache.delete(STORAGE_CACHE_KEY)
        usage = storage_usage()
        self.assertEqual([s["key"] for s in usage["segments"]], ["public", "private", "other", "free"])
        self.assertGreaterEqual(sum(s["bytes"] for s in usage["segments"]), usage["used"] + usage["free"])


class DashboardInsightsTests(BaseTestCase):
    def test_overview_shows_locations_and_storage(self):
        VisitorCounter.objects.create(pk=1, total=5)
        VisitorCountry.objects.create(code="CA", visitors=3)
        self.client.force_login(self.make_user("owner", staff=True))
        response = self.client.get(reverse("dashboard:home"))
        self.assertContains(response, "Visitors location")
        self.assertContains(response, 'data-region="CA"')
        self.assertContains(response, "Unknown")
        self.assertContains(response, "Storage capacity")
