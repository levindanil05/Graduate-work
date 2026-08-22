from datetime import datetime, timezone

from django.test import SimpleTestCase

from plans.archive_naming import apply_archive_suffix, choose_archive_filename


class ArchiveNamingTests(SimpleTestCase):
    def test_date_suffix(self):
        dt = datetime(2024, 9, 1, 14, 32, 7, tzinfo=timezone.utc)
        self.assertEqual(
            apply_archive_suffix('Ucheb_plan_test.plx', dt),
            'Ucheb_plan_test (2024-09-01).plx',
        )

    def test_collision_adds_time(self):
        dt = datetime(2024, 9, 1, 14, 32, 7, tzinfo=timezone.utc)
        occupied = {'Ucheb_plan_test (2024-09-01).plx'}
        name = choose_archive_filename('Ucheb_plan_test.plx', dt, occupied)
        self.assertIn('17-32-07', name)
