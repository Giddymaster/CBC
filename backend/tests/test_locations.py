"""The cascading county → sub-county → ward lookup behind the registration form.

The dataset is bundled (`apps/schools/locations.json`), so these assert both the
shape of the endpoint and that the data is complete: Kenya has 47 counties, and
every level must narrow to the one above it.
"""

from rest_framework.test import APITestCase


class LocationsEndpointTests(APITestCase):
    def test_no_params_returns_all_47_counties_sorted(self):
        res = self.client.get("/api/locations/")
        self.assertEqual(res.status_code, 200)
        counties = res.data["counties"]
        self.assertEqual(len(counties), 47)
        self.assertEqual(counties, sorted(counties))
        # A county from each former province, so it isn't a truncated list.
        for expected in ("Nairobi", "Mombasa", "Kisumu", "Bomet", "West Pokot"):
            self.assertIn(expected, counties)

    def test_a_county_narrows_to_its_subcounties(self):
        res = self.client.get("/api/locations/", {"county": "Nairobi"})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["county"], "Nairobi")
        subs = res.data["subcounties"]
        self.assertTrue(subs)
        self.assertEqual(subs, sorted(subs))
        self.assertIn("Westlands", subs)

    def test_a_subcounty_narrows_to_its_wards(self):
        res = self.client.get(
            "/api/locations/", {"county": "Nairobi", "subcounty": "Westlands"}
        )
        self.assertEqual(res.status_code, 200)
        wards = res.data["wards"]
        self.assertTrue(wards)
        self.assertEqual(wards, sorted(wards))

    def test_lookup_is_case_insensitive(self):
        """The form sends what the user picked; a stored 'nairobi' must still match."""
        res = self.client.get("/api/locations/", {"county": "nairobi"})
        self.assertTrue(res.data["subcounties"])

    def test_the_upstream_west_pokot_typo_is_fixed(self):
        counties = self.client.get("/api/locations/").data["counties"]
        self.assertIn("West Pokot", counties)
        self.assertNotIn("West pokot", counties)

    def test_an_unknown_county_returns_an_empty_list_not_an_error(self):
        res = self.client.get("/api/locations/", {"county": "Atlantis"})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["subcounties"], [])

    def test_an_unknown_subcounty_returns_empty_wards(self):
        res = self.client.get(
            "/api/locations/", {"county": "Nairobi", "subcounty": "Nowhere"}
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["wards"], [])

    def test_the_endpoint_is_open_without_authentication(self):
        """A school registers before it has any account, so the picker can't
        require a login."""
        self.assertEqual(self.client.get("/api/locations/").status_code, 200)
