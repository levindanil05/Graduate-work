from external_sync.models import ReplicaSyncState, RemoteRole

REPLICA_SYNC_STATE_LABELS = {
    ReplicaSyncState.IN_SYNC: 'Синхронизирована',
    ReplicaSyncState.PENDING_PUSH: 'Ожидает отправки',
    ReplicaSyncState.PAUSED_BY_SWITCH: 'Отправка выключена',
    ReplicaSyncState.CONFLICT: 'Расхождение',
    ReplicaSyncState.MISSING_REMOTE: 'Нет на диске',
    ReplicaSyncState.STALE: 'Данные могут устареть',
}

REPLICA_ROLE_LABELS = {
    RemoteRole.ACTIVE: 'Актуальная',
    RemoteRole.ARCHIVE: 'Архивная',
    RemoteRole.IGNORED: 'Игнорируется',
}


def replica_sync_state_label(state: str) -> str:
    return REPLICA_SYNC_STATE_LABELS.get(state, state)


def replica_role_label(role: str) -> str:
    return REPLICA_ROLE_LABELS.get(role, role)
