"""Реестр видов документов.

Вид без собственного разбора файла добавляется записью в settings.DOCUMENT_TYPES.
Ключи naming_strategy и metadata_extractor ссылаются на классы, которые живут в коде.
"""

from __future__ import annotations

from dataclasses import dataclass

from django.conf import settings
from django.core.exceptions import ValidationError


class UnknownDocumentType(LookupError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class DocumentTypeConfigError(LookupError):
    def __init__(self, code: str, key: str) -> None:
        self.code = code
        self.key = key
        super().__init__(f'{code}: {key}')


@dataclass(frozen=True)
class DocumentTypeSpec:
    code: str
    label: str
    file_extensions: tuple[str, ...]
    naming_strategy: str
    metadata_extractor: str | None = None


DEFAULT_DOCUMENT_TYPES: tuple[dict, ...] = (
    {
        'code': 'plx',
        'label': 'Учебный план (PLX)',
        'file_extensions': ('.plx',),
        'naming_strategy': 'plx',
        'metadata_extractor': 'plx',
    },
    {
        'code': 'generic',
        'label': 'Общий документ',
        'file_extensions': (),
        'naming_strategy': 'filename',
        'metadata_extractor': None,
    },
)


def _raw_config() -> list[dict]:
    configured = getattr(settings, 'DOCUMENT_TYPES', None)
    if not configured:
        return [dict(item) for item in DEFAULT_DOCUMENT_TYPES]
    return list(configured)


def list_specs() -> list[DocumentTypeSpec]:
    specs: list[DocumentTypeSpec] = []
    for item in _raw_config():
        extractor = item.get('metadata_extractor') or None
        specs.append(
            DocumentTypeSpec(
                code=str(item['code']),
                label=str(item['label']),
                file_extensions=tuple(item.get('file_extensions') or ()),
                naming_strategy=str(item.get('naming_strategy') or 'filename'),
                metadata_extractor=str(extractor) if extractor else None,
            )
        )
    return specs


def get_spec(code: str) -> DocumentTypeSpec:
    key = type_code(code)
    for spec in list_specs():
        if spec.code == key:
            return spec
    raise UnknownDocumentType(key)


def is_known(code: str) -> bool:
    key = type_code(code)
    return any(spec.code == key for spec in list_specs())


def label_for(code: str) -> str:
    try:
        return get_spec(code).label
    except UnknownDocumentType:
        return type_code(code)


def type_code(document_type: object) -> str:
    return str(document_type)


def validate_document_type(value: str) -> None:
    if not is_known(value):
        raise ValidationError(
            'Неизвестный вид документа: %(code)s',
            params={'code': value},
        )


def build_naming_strategy(code: str):
    from documents.strategies import GenericNamingStrategy, PlxNamingStrategy

    spec = get_spec(code)
    classes = {
        'plx': PlxNamingStrategy,
        'filename': GenericNamingStrategy,
    }
    cls = classes.get(spec.naming_strategy)
    if cls is None:
        raise DocumentTypeConfigError(spec.code, spec.naming_strategy)
    return cls()


def build_metadata_extractor(code: str):
    spec = get_spec(code)
    if not spec.metadata_extractor:
        return None
    from documents.infra.extractors import PlxMetadataExtractor

    classes = {
        'plx': PlxMetadataExtractor,
    }
    cls = classes.get(spec.metadata_extractor)
    if cls is None:
        raise DocumentTypeConfigError(spec.code, spec.metadata_extractor)
    return cls()
