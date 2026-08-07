"""The county → sub-county → ward lookup that backs the cascading pickers."""

from rest_framework.test import APITestCase

from apps.schools import locations
from tests.factories import make_school, make_user


class LocationDataTests(APITestCase):
    def test_the_dataset_is_complete(self):
        """47 counties and the full ward set — a missing county would silently
        block schools there from registering."""
        self.assertEqual(len(locations.counties()), 47)
        self.assertIn("Nairobi", locations.counties())
        self.assertIn("Bomet", locations.counties())
        self.assertIn("Kericho", locations.counties())

    def test_wards_total_matches_the_iebc_count(self):
        total = sum(
            len(locations.wards(county, sub))
            for county in locations.counties()
            for sub in locations.subcounties(county)
        )
        self.assertGreater(total, 1400)  # official is ~1,450

    def test_subcounties_narrow_to_the_county(self):
        subs = locations.subcounties("Nairobi")
        self.assertIn("Westlands", subs)
        self.assertNotIn("Changamwe", subs)  # that is Mombasa's

    def test_wards_narrow_to_the_subcounty(self):
        wards = locations.wards("Nairobi", "Westlands")
        self.assertTrue(wards)
        # A ward from another sub-county must not appear here.
        self.assertNotIn("Port Reitz", wards)

    def test_lookup_is_case_insensitive(self):
        self.assertEqual(
            locations.subcounties("nairobi"), locations.subcounties("Nairobi")
        )

    def test_the_upstream_typo_is_fixed(self):
        self.assertIn("West Pokot", locations.counties())
        self.assertNotIn("West pokot", locations.counties())

    def test_an_unknown_county_returns_nothing_rather_than_erroring(self):
        self.assertEqual(locations.subcounties("Atlantis"), [])
        self.assertEqual(locations.wards("Atlantis", "Nowhere"), [])


class LocationApiTests(APITestCase):
    def setUp(self):
        self.user = make_user(make_school(), "ADMIN")
        self.client.force_authenticate(self.user)

    def test_no_params_lists_counties(self):
        res = self.client.get("/api/locations/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(res.data["counties"]), 47)

    def test_county_param_lists_its_subcounties(self):
        res = self.client.get("/api/locations/?county=Nairobi")
        self.assertEqual(res.status_code, 200)
        self.assertIn("Westlands", res.data["subcounties"])

    def test_county_and_subcounty_list_wards(self):
        res = self.client.get("/api/locations/?county=Nairobi&subcounty=Westlands")
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.data["wards"])

    def test_it_needs_authentication(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get("/api/locations/").status_code, 401)
