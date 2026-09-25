from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase

from accounts.roles import Role
from documents.entities import VersionStatus
from documents.factory import build_document_service
from documents.models import Document, DocumentVersion
from documents.services import UploadRequest
from documents.entities import DocumentType


User = get_user_model()


class ApproveTransitionTests(TestCase):
    _sample_plx_a = Path(__file__).resolve().parents[4] / 'userfiles' / 'ХТФ' / 'ПЭБЖ' / 'Ucheb_plan_18.03.02_P_OOS_O_NOR_HTF_PEBG_2021.plx'
    _sample_plx_b = Path(__file__).resolve().parents[4] / 'userfiles' / 'ХТФ' / 'ПЭБЖ' / 'Ucheb_plan_18.03.02_P_OOS_O_NOR_HTF_PEBG_2022.plx'

    def setUp(self):
        for role in Role:
            Group.objects.get_or_create(name=role.value)
        self.user = User.objects.create_user(username='approver', password='x')
        self.user.groups.add(Group.objects.get(name=Role.ADMINISTRATOR.value))
        # Разработчик УП нужен для загрузки; админ покрывает оба действия.
        # Для явной проверки цепочки submit+approve оставляем администратора.

    def _copy_sample(self, source: Path | None = None) -> Path:
        src = source or self._sample_plx_a
        fd, name = tempfile.mkstemp(suffix='.plx')
        import os
        os.close(fd)
        tmp = Path(name)
        shutil.copy2(src, tmp)
        return tmp

    def test_approve_archives_previous_and_sets_approved_version(self):
        service = build_document_service()
        path_v1 = self._copy_sample()
        path_v2 = self._copy_sample(self._sample_plx_b)

        try:
            result = service.upload_new_document(
                UploadRequest(
                    user_id=self.user.id,
                    document_type=DocumentType.PLX,
                    file_path=path_v1,
                    source_filename='plan_v1.plx',
                )
            )
            v1 = DocumentVersion.objects.get(pk=result.version_id)
            service.transition_version_status(
                version_id=v1.id,
                actor_user_id=self.user.id,
                target_status=VersionStatus.ON_REVIEW,
                action_comment='',
                allow_without_comment=True,
            )
            service.transition_version_status(
                version_id=v1.id,
                actor_user_id=self.user.id,
                target_status=VersionStatus.APPROVED,
                action_comment='',
                allow_without_comment=True,
            )

            result2 = service.upload_new_version(
                result.document_id,
                UploadRequest(
                    user_id=self.user.id,
                    document_type=DocumentType.PLX,
                    file_path=path_v2,
                    source_filename='plan_v2.plx',
                    skip_filename_check=True,
                ),
            )
            v2 = DocumentVersion.objects.get(pk=result2.version_id)
            service.transition_version_status(
                version_id=v2.id,
                actor_user_id=self.user.id,
                target_status=VersionStatus.ON_REVIEW,
                action_comment='',
                allow_without_comment=True,
            )
            service.transition_version_status(
                version_id=v2.id,
                actor_user_id=self.user.id,
                target_status=VersionStatus.APPROVED,
                action_comment='',
                allow_without_comment=True,
            )

            v1.refresh_from_db()
            v2.refresh_from_db()
            document = Document.objects.get(pk=result.document_id)

            self.assertEqual(v1.status, VersionStatus.ARCHIVED.value)
            self.assertEqual(v2.status, VersionStatus.APPROVED.value)
            self.assertEqual(document.approved_version_id, v2.id)
            self.assertTrue(v2.storage_key.startswith(f'documents/{document.id}/'))
        finally:
            path_v1.unlink(missing_ok=True)
            path_v2.unlink(missing_ok=True)
