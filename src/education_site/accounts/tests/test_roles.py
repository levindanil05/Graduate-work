from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase

from accounts.permissions import RolePermissionService
from accounts.roles import Role
from documents.entities import Document, DocumentVersion, VersionStatus


User = get_user_model()


class RolePermissionMatrixTests(TestCase):
    def setUp(self):
        for role in Role:
            Group.objects.get_or_create(name=role.value)
        self.perms = RolePermissionService()
        self.document = Document()
        self.version_new = DocumentVersion(status=VersionStatus.NEW)
        self.version_review = DocumentVersion(status=VersionStatus.ON_REVIEW)
        self.version_fix = DocumentVersion(status=VersionStatus.NEEDS_FIX)

    def _user_with(self, *roles: Role) -> User:
        user = User.objects.create_user(
            username=f'u_{"_".join(r.value for r in roles)}',
            password='x',
        )
        for role in roles:
            user.groups.add(Group.objects.get(name=role.value))
        return user

    def test_reader_cannot_upload_or_approve(self):
        user = self._user_with(Role.READER)
        self.assertFalse(self.perms.can_upload_version(user.id, self.document))
        self.assertFalse(
            self.perms.can_transition(user.id, self.version_review, VersionStatus.APPROVED)
        )

    def test_developer_can_submit_and_upload(self):
        user = self._user_with(Role.CURRICULUM_DEVELOPER)
        self.assertTrue(self.perms.can_upload_version(user.id, self.document))
        self.assertTrue(
            self.perms.can_transition(user.id, self.version_new, VersionStatus.ON_REVIEW)
        )
        self.assertTrue(
            self.perms.can_transition(user.id, self.version_fix, VersionStatus.ON_REVIEW)
        )
        self.assertFalse(
            self.perms.can_transition(user.id, self.version_review, VersionStatus.APPROVED)
        )

    def test_reviewer_can_approve_not_upload(self):
        user = self._user_with(Role.REVIEWER)
        self.assertFalse(self.perms.can_upload_version(user.id, self.document))
        self.assertTrue(
            self.perms.can_transition(user.id, self.version_review, VersionStatus.APPROVED)
        )
        self.assertTrue(
            self.perms.can_transition(user.id, self.version_review, VersionStatus.NEEDS_FIX)
        )
        self.assertFalse(self.perms.can_manage_sync(user.id))

    def test_manager_can_sync_not_hard_delete(self):
        user = self._user_with(Role.MANAGER)
        self.assertTrue(self.perms.can_manage_sync(user.id))
        self.assertTrue(
            self.perms.can_transition(user.id, self.version_review, VersionStatus.APPROVED)
        )
        self.assertFalse(self.perms.can_hard_delete(user.id, self.document))
        self.assertFalse(self.perms.can_upload_version(user.id, self.document))

    def test_admin_full_access(self):
        user = self._user_with(Role.ADMINISTRATOR)
        self.assertTrue(self.perms.can_upload_version(user.id, self.document))
        self.assertTrue(self.perms.can_manage_sync(user.id))
        self.assertTrue(self.perms.can_hard_delete(user.id, self.document))

    def test_superuser_is_administrator(self):
        user = User.objects.create_superuser('root', 'r@e.com', 'x')
        self.assertTrue(self.perms.can_hard_delete(user.id, self.document))
        self.assertTrue(self.perms.can_manage_sync(user.id))

    def test_system_actor_allowed(self):
        self.assertTrue(self.perms.can_upload_version(0, self.document))
        self.assertTrue(
            self.perms.can_transition(0, self.version_review, VersionStatus.APPROVED)
        )
