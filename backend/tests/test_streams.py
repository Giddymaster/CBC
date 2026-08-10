"""The stream list a class picker offers."""

from rest_framework.test import APITestCase

from apps.students.models import ClassGroup
from tests.factories import make_learner, make_school, make_user


class GradeStreamsTests(APITestCase):
    def setUp(self):
        self.school = make_school()
        self.admin = make_user(self.school, "ADMIN")

    def test_streams_come_from_the_learners_not_only_the_class_groups(self):
        """A school that imported learners into South without ever creating
        that class group must still be able to pick South."""
        ClassGroup.objects.create(school=self.school, grade=5, stream="North")
        make_learner(self.school, grade=5, stream="North")
        make_learner(self.school, grade=5, stream="South")
        self.client.force_authenticate(self.admin)
        res = self.client.get("/api/school/streams/?grade=5")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["streams"], ["North", "South"])

    def test_an_empty_stream_is_reported_so_those_learners_are_not_lost(self):
        make_learner(self.school, grade=7, stream="")
        self.client.force_authenticate(self.admin)
        res = self.client.get("/api/school/streams/?grade=7")
        self.assertEqual(res.data["streams"], [])
        self.assertTrue(res.data["unstreamed"])

    def test_without_a_grade_it_lists_the_whole_school(self):
        make_learner(self.school, grade=4, stream="East")
        make_learner(self.school, grade=9, stream="West")
        self.client.force_authenticate(self.admin)
        res = self.client.get("/api/school/streams/")
        self.assertEqual(res.data["streams"], ["East", "West"])

    def test_a_parent_cannot_read_it(self):
        self.client.force_authenticate(make_user(self.school, "PARENT"))
        self.assertEqual(self.client.get("/api/school/streams/").status_code, 403)
