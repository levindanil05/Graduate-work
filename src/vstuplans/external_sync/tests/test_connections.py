from django.test import TestCase

from external_sync.models import ExternalConnection, WriteMode


class ConnectionValidationTests(TestCase):
    def setUp(self):
        self.uo = ExternalConnection.objects.create(
            slug='uo_test',
            name='UO test',
            credential_ref='TEST',
            write_mode=WriteMode.READ_ONLY,
        )
        self.mike = ExternalConnection.objects.create(
            slug='mike_test',
            name='Mike test',
            credential_ref='TEST2',
            write_mode=WriteMode.READ_WRITE,
        )

    def test_readonly_cannot_enable_push_on_save(self):
        self.uo.push_enabled = True
        self.uo.save()
        self.uo.refresh_from_db()
        self.assertFalse(self.uo.push_enabled)

    def test_only_one_pull_enabled(self):
        self.uo.pull_enabled = True
        self.uo.save()
        self.mike.pull_enabled = True
        self.mike.save()
        self.uo.refresh_from_db()
        self.assertFalse(self.uo.pull_enabled)
        self.assertTrue(self.mike.pull_enabled)
