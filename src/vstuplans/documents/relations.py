"""Сервис связей компаньонов с главными документами."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from django.db import transaction
from django.utils.translation import gettext as _

from documents.document_types import CompanionSlot, companion_slots_for, slot_for
from documents.models import Document, DocumentRelation, DocumentVersion
from documents.services import DomainValidationError


@dataclass(frozen=True)
class RelationView:
    relation: DocumentRelation
    companion: Document
    slot: CompanionSlot | None


def _would_create_cycle(companion_id: UUID, primary_id: UUID) -> bool:
    """True, если primary уже зависит (прямо или транзитивно) от companion."""
    if companion_id == primary_id:
        return True
    frontier = [companion_id]
    seen: set[UUID] = {companion_id}
    while frontier:
        current = frontier.pop()
        parents = DocumentRelation.objects.filter(
            source_document_id=current,
            is_current=True,
        ).values_list('target_document_id', flat=True)
        for parent_id in parents:
            if parent_id == primary_id:
                return True
            if parent_id not in seen:
                seen.add(parent_id)
                frontier.append(parent_id)
    return False


def _count_current_on_anchor(
    *,
    target_document_id: UUID,
    target_version_id: UUID | None,
    slot_code: str,
    exclude_source_id: UUID | None = None,
) -> int:
    qs = DocumentRelation.objects.filter(
        target_document_id=target_document_id,
        slot_code=slot_code,
        is_current=True,
    )
    if target_version_id is None:
        qs = qs.filter(target_version__isnull=True)
    else:
        qs = qs.filter(target_version_id=target_version_id)
    if exclude_source_id is not None:
        qs = qs.exclude(source_document_id=exclude_source_id)
    return qs.count()


def _check_cardinality(
    slot: CompanionSlot,
    *,
    target_document_id: UUID,
    target_version_id: UUID | None,
    exclude_source_id: UUID | None = None,
) -> None:
    if slot.cardinality in {'0..n'}:
        return
    count = _count_current_on_anchor(
        target_document_id=target_document_id,
        target_version_id=target_version_id,
        slot_code=slot.code,
        exclude_source_id=exclude_source_id,
    )
    if slot.cardinality in {'0..1', '1'} and count >= 1:
        raise DomainValidationError(
            _('Для этого слота на выбранном якоре уже есть документ')
        )


@transaction.atomic
def bind_companion(
    *,
    companion: Document,
    primary: Document,
    slot_code: str,
    target_version: DocumentVersion | None = None,
) -> DocumentRelation:
    slot = slot_for(primary.document_type, slot_code)
    if slot is None:
        raise DomainValidationError(_('Слот «%(code)s» не настроен у этого вида') % {'code': slot_code})
    if companion.document_type != slot.code:
        raise DomainValidationError(_('Вид компаньона не совпадает со слотом'))

    if slot.anchor == 'edition':
        if target_version is None:
            raise DomainValidationError(_('Для слота с якорем «редакция» нужна редакция'))
        if target_version.document_id != primary.id:
            raise DomainValidationError(_('Редакция не принадлежит главному документу'))
    else:
        target_version = None

    if _would_create_cycle(companion.id, primary.id):
        raise DomainValidationError(_('Нельзя создать цикл связей документов'))

    version_id = target_version.id if target_version else None
    _check_cardinality(
        slot,
        target_document_id=primary.id,
        target_version_id=version_id,
        exclude_source_id=companion.id,
    )

    # Снимаем прежние текущие связи этого компаньона в том же слоте.
    DocumentRelation.objects.filter(
        source_document=companion,
        slot_code=slot_code,
        is_current=True,
    ).update(is_current=False)

    relation = DocumentRelation.objects.create(
        source_document=companion,
        target_document=primary,
        target_version=target_version,
        slot_code=slot_code,
        is_current=True,
    )
    return relation


@transaction.atomic
def rebind_companion(
    *,
    relation: DocumentRelation,
    target_version: DocumentVersion,
) -> DocumentRelation:
    """Перенести текущую связь на другую редакцию того же главного документа."""
    if not relation.is_current:
        raise DomainValidationError(_('Перепривязать можно только текущую связь'))
    primary = relation.target_document
    if target_version.document_id != primary.id:
        raise DomainValidationError(_('Редакция не принадлежит главному документу'))

    slot = slot_for(primary.document_type, relation.slot_code)
    if slot is None or slot.anchor != 'edition':
        raise DomainValidationError(_('Перепривязка доступна только для слотов с якорем «редакция»'))

    if relation.target_version_id == target_version.id:
        return relation

    _check_cardinality(
        slot,
        target_document_id=primary.id,
        target_version_id=target_version.id,
        exclude_source_id=relation.source_document_id,
    )

    relation.is_current = False
    relation.save(update_fields=['is_current', 'updated_at'])

    return DocumentRelation.objects.create(
        source_document=relation.source_document,
        target_document=primary,
        target_version=target_version,
        slot_code=relation.slot_code,
        is_current=True,
    )


@transaction.atomic
def unbind_companion(relation: DocumentRelation) -> None:
    if relation.is_current:
        relation.is_current = False
        relation.save(update_fields=['is_current', 'updated_at'])


def list_companions_for_primary(
    primary: Document,
    *,
    version: DocumentVersion | None = None,
) -> list[RelationView]:
    slots = {s.code: s for s in companion_slots_for(primary.document_type)}
    qs = DocumentRelation.objects.filter(
        target_document=primary,
        is_current=True,
    ).select_related('source_document', 'target_version')

    views: list[RelationView] = []
    for rel in qs:
        slot = slots.get(rel.slot_code)
        if slot and slot.anchor == 'edition' and version is not None:
            if rel.target_version_id != version.id:
                # Для отображения на карточке текущей редакции — только её слоты edition;
                # остальные edition-связи всё равно покажем в общем блоке с пометкой редакции.
                pass
        views.append(
            RelationView(relation=rel, companion=rel.source_document, slot=slot)
        )
    return views


def current_relation_for_companion(companion: Document) -> DocumentRelation | None:
    return (
        DocumentRelation.objects.filter(source_document=companion, is_current=True)
        .select_related('target_document', 'target_version')
        .first()
    )


def direct_dependents(primary: Document) -> list[Document]:
    rels = DocumentRelation.objects.filter(
        target_document=primary,
        is_current=True,
    ).select_related('source_document')
    return [r.source_document for r in rels]


def detach_all_from_primary(primary: Document) -> int:
    return DocumentRelation.objects.filter(
        target_document=primary,
        is_current=True,
    ).update(is_current=False)


def orphan_companion_queryset(document_type: str | None = None):
    """Документы-компаньоны без текущей связи с главным."""
    linked_ids = DocumentRelation.objects.filter(is_current=True).values_list(
        'source_document_id', flat=True
    )
    # Виды, которые встречаются как слоты у каких-либо главных.
    companion_codes: set[str] = set()
    from documents.document_types import list_specs

    for spec in list_specs():
        for slot in spec.companions:
            companion_codes.add(slot.code)

    qs = Document.objects.filter(document_type__in=companion_codes).exclude(id__in=linked_ids)
    if document_type:
        qs = qs.filter(document_type=document_type)
    return qs.select_related('current_version').order_by('canonical_name')


def documents_of_type(document_type: str, *, orphans_only: bool = False):
    if orphans_only:
        return orphan_companion_queryset(document_type)
    return (
        Document.objects.filter(document_type=document_type)
        .select_related('current_version')
        .order_by('canonical_name')
    )
