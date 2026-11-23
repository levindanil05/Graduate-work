from __future__ import annotations

import os
import tempfile
from pathlib import Path

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase

from accounts.roles import Role
from documents.entities import VersionStatus
from documents.factory import build_document_service
from documents.lifecycle import (
    get_lifecycle_profile,
    get_rule_for_type,
    list_rules_for_type,
    reset_lifecycle_provider,
    status_label_for_type,
)
from documents.models import Document, DocumentRelation, DocumentVersion
from documents.relations import bind_companion, orphan_companion_queryset, rebind_companion
from documents.services import DomainValidationError, UploadRequest
from documents.workflow_rules import get_rule
from plans.companion_views import companion_slots_context


User = get_user_model()


class CompanionLifecycleTests(TestCase):
    def setUp(self):
        reset_lifecycle_provider()

    def test_printed_form_short_lifecycle(self):
        profile = get_lifecycle_profile('printed_form')
        self.assertEqual(status_label_for_type('new', 'printed_form'), 'Черновик')
        self.assertEqual(status_label_for_type('approved', 'printed_form'), 'Утверждён')
        codes = {t.from_status for t in profile.transitions}
        self.assertEqual(codes, {'new'})
        rule = get_rule_for_type(VersionStatus.NEW, VersionStatus.APPROVED, document_type='printed_form')
        self.assertIsNotNone(rule)
        self.assertEqual(rule.action.value, 'approve')
        # Нет согласования УО у печатной формы.
        self.assertIsNone(
            get_rule_for_type(VersionStatus.NEW, VersionStatus.ON_REVIEW, document_type='printed_form')
        )

    def test_plx_lifecycle_matches_legacy_submit(self):
        legacy = get_rule(VersionStatus.NEW, VersionStatus.ON_REVIEW)
        typed = get_rule_for_type(VersionStatus.NEW, VersionStatus.ON_REVIEW, document_type='plx')
        self.assertIsNotNone(legacy)
        self.assertIsNotNone(typed)
        self.assertEqual(legacy.action, typed.action)
        self.assertEqual(legacy.to_status, typed.to_status)
        rules = list_rules_for_type(VersionStatus.NEW, document_type='plx')
        actions = {r.action.value for r in rules}
        self.assertIn('submit', actions)
        self.assertIn('move_to_trash', actions)


class CompanionRelationTests(TestCase):
    def setUp(self):
        reset_lifecycle_provider()
        for role in Role:
            Group.objects.get_or_create(name=role.value)
        self.admin = User.objects.create_user(username='admin', password='x')
        self.admin.groups.add(Group.objects.get(name=Role.ADMINISTRATOR.value))
        self.reviewer = User.objects.create_user(username='reviewer', password='x')
        self.reviewer.groups.add(Group.objects.get(name=Role.REVIEWER.value))
        self.developer = User.objects.create_user(username='dev', password='x')
        self.developer.groups.add(Group.objects.get(name=Role.CURRICULUM_DEVELOPER.value))

        self.primary = Document.objects.create(
            document_type='plx',
            canonical_name='plan.plx',
        )
        self.v1 = DocumentVersion.objects.create(
            document=self.primary,
            status=VersionStatus.NEW.value,
            version_number=1,
            source_filename='plan.plx',
            storage_key='k1',
            content_hash='h1',
        )
        self.v2 = DocumentVersion.objects.create(
            document=self.primary,
            status=VersionStatus.NEW.value,
            version_number=2,
            source_filename='plan.plx',
            storage_key='k2',
            content_hash='h2',
        )
        self.primary.current_version = self.v2
        self.primary.save(update_fields=['current_version'])

    def _make_printed_form(self, name: str = 'form.pdf') -> Document:
        companion = Document.objects.create(
            document_type='printed_form',
            canonical_name=name,
        )
        version = DocumentVersion.objects.create(
            document=companion,
            status=VersionStatus.NEW.value,
            version_number=1,
            source_filename=name,
            storage_key=f'sk-{name}',
            content_hash=f'h-{name}',
        )
        companion.current_version = version
        companion.save(update_fields=['current_version'])
        return companion

    def test_bind_and_rebind(self):
        companion = self._make_printed_form()
        rel = bind_companion(
            companion=companion,
            primary=self.primary,
            slot_code='printed_form',
            target_version=self.v1,
        )
        self.assertTrue(rel.is_current)
        self.assertEqual(rel.target_version_id, self.v1.id)

        new_rel = rebind_companion(relation=rel, target_version=self.v2)
        self.assertTrue(new_rel.is_current)
        self.assertEqual(new_rel.target_version_id, self.v2.id)
        rel.refresh_from_db()
        self.assertFalse(rel.is_current)

    def test_rebind_button_only_when_other_edition_has_companion(self):
        companion = self._make_printed_form()
        # Текущая редакция — v2, компаньон на v1 → кнопка нужна.
        bind_companion(
            companion=companion,
            primary=self.primary,
            slot_code='printed_form',
            target_version=self.v1,
        )
        slots = companion_slots_context(self.primary, self.reviewer.id)
        printed = next(s for s in slots if s['slot'].code == 'printed_form')
        self.assertTrue(printed['can_rebind'])
        self.assertEqual(printed['label_plural'], 'Печатные формы')

        # После переноса на текущую v2 — перепривязывать нечего.
        current_rel = DocumentRelation.objects.get(
            source_document=companion, is_current=True
        )
        rebind_companion(relation=current_rel, target_version=self.v2)
        slots_after = companion_slots_context(self.primary, self.reviewer.id)
        printed_after = next(s for s in slots_after if s['slot'].code == 'printed_form')
        self.assertFalse(printed_after['can_rebind'])

    def test_cardinality_blocks_second_on_same_edition(self):
        first = self._make_printed_form('a.pdf')
        second = self._make_printed_form('b.pdf')
        bind_companion(
            companion=first,
            primary=self.primary,
            slot_code='printed_form',
            target_version=self.v1,
        )
        with self.assertRaises(DomainValidationError):
            bind_companion(
                companion=second,
                primary=self.primary,
                slot_code='printed_form',
                target_version=self.v1,
            )

    def test_orphan_after_detach(self):
        companion = self._make_printed_form()
        bind_companion(
            companion=companion,
            primary=self.primary,
            slot_code='printed_form',
            target_version=self.v1,
        )
        DocumentRelation.objects.filter(source_document=companion).update(is_current=False)
        self.assertTrue(orphan_companion_queryset('printed_form').filter(pk=companion.pk).exists())

    def test_reviewer_can_upload_printed_form_developer_cannot(self):
        fd, name = tempfile.mkstemp(suffix='.pdf')
        os.write(fd, b'%PDF-1.4')
        os.close(fd)
        path = Path(name)
        service = build_document_service()
        try:
            result = service.upload_new_document(
                UploadRequest(
                    user_id=self.reviewer.id,
                    document_type='printed_form',
                    file_path=path,
                    source_filename='form.pdf',
                )
            )
            self.assertEqual(result.status, VersionStatus.NEW.value)
            with self.assertRaises(DomainValidationError):
                service.upload_new_document(
                    UploadRequest(
                        user_id=self.developer.id,
                        document_type='printed_form',
                        file_path=path,
                        source_filename='form2.pdf',
                    )
                )
        finally:
            path.unlink(missing_ok=True)
