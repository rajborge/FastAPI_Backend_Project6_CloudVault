from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.core.enum import PermissionRole, ResourceType
from app.services.PermissionService import PermissionService


def test_file_owner_can_grant_a_permission():
    owner = SimpleNamespace(id=uuid4())
    target = SimpleNamespace(id=uuid4())
    file = SimpleNamespace(user_id=owner.id)
    service = PermissionService.__new__(PermissionService)
    service.file_repository = Mock()
    service.file_repository.get_by_id.return_value = file
    service.permission_repository = Mock()
    service.permission_repository.get_explicit_permission.return_value = None
    service.user_repository = Mock()
    service.user_repository.get_by_id.return_value = target
    service.db = Mock()

    permission = service.grant_permission(
        actor=owner,
        target_user_id=target.id,
        resource_type=ResourceType.FILE,
        resource_id=uuid4(),
        role=PermissionRole.COMMENTER,
    )

    assert permission.user_id == target.id
    assert permission.role == PermissionRole.COMMENTER
    service.permission_repository.create.assert_called_once_with(permission)
    service.db.commit.assert_called_once()


def test_non_owner_cannot_grant_permission():
    owner = SimpleNamespace(id=uuid4())
    actor = SimpleNamespace(id=uuid4())
    service = PermissionService.__new__(PermissionService)
    service.file_repository = Mock()
    service.file_repository.get_by_id.return_value = SimpleNamespace(user_id=owner.id)
    service.permission_repository = Mock()
    service.permission_repository.get_explicit_permission.return_value = SimpleNamespace(
        role=PermissionRole.VIEWER
    )

    with pytest.raises(HTTPException) as error:
        service.grant_permission(
            actor=actor,
            target_user_id=uuid4(),
            resource_type=ResourceType.FILE,
            resource_id=uuid4(),
            role=PermissionRole.EDITOR,
        )

    assert error.value.status_code == 403


def test_nearest_ancestor_permission_is_inherited():
    actor_id = uuid4()
    owner_id = uuid4()
    child_id = uuid4()
    parent_id = uuid4()
    file_id = uuid4()
    child = SimpleNamespace(id=child_id, parent_id=parent_id, user_id=owner_id)
    parent = SimpleNamespace(id=parent_id, parent_id=None, user_id=owner_id)
    inherited = SimpleNamespace(role=PermissionRole.VIEWER)
    service = PermissionService.__new__(PermissionService)
    service.file_repository = Mock()
    service.file_repository.get_by_id.return_value = SimpleNamespace(
        user_id=owner_id,
        folder_id=child_id,
    )
    service.folder_repository = Mock()
    service.folder_repository.get_by_id.side_effect = [child, parent]
    service.permission_repository = Mock()
    service.permission_repository.get_explicit_permission.side_effect = [None, None, inherited]

    role = service.get_effective_permission(
        resource_type=ResourceType.FILE,
        resource_id=file_id,
        user=SimpleNamespace(id=actor_id),
    )

    assert role == PermissionRole.VIEWER


def test_commenter_can_view_but_cannot_edit():
    service = PermissionService.__new__(PermissionService)
    service.get_effective_permission = Mock(return_value=PermissionRole.COMMENTER)

    service.check_permissions(
        user=SimpleNamespace(id=uuid4()),
        resource_type=ResourceType.FILE,
        resource_id=uuid4(),
        required_role=PermissionRole.VIEWER,
    )
    with pytest.raises(HTTPException) as error:
        service.check_permissions(
            user=SimpleNamespace(id=uuid4()),
            resource_type=ResourceType.FILE,
            resource_id=uuid4(),
            required_role=PermissionRole.EDITOR,
        )

    assert error.value.status_code == 403
