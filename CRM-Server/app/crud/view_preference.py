import json
from uuid import uuid4
from typing import Optional

from sqlalchemy.orm import Session

from app.models.view_preference import ViewPreference, ViewPreferenceScope
from app.schemas.view_preference import ViewPreferenceConfig


class ViewPreferenceCRUD:
    def get(
        self,
        db: Session,
        *,
        team_id: int,
        view_key: str,
        scope: str,
        user_id: int,
        preference_key: str = "default",
    ) -> Optional[ViewPreference]:
        return db.query(ViewPreference).filter(
            ViewPreference.team_id == team_id,
            ViewPreference.view_key == view_key,
            ViewPreference.scope == scope,
            ViewPreference.user_id == user_id,
            ViewPreference.preference_key == preference_key,
        ).first()

    def get_personal(self, db: Session, *, team_id: int, view_key: str, user_id: int) -> Optional[ViewPreference]:
        return self.get(
            db,
            team_id=team_id,
            view_key=view_key,
            scope=ViewPreferenceScope.PERSONAL.value,
            user_id=user_id,
        )

    def get_team(self, db: Session, *, team_id: int, view_key: str) -> Optional[ViewPreference]:
        return self.get(
            db,
            team_id=team_id,
            view_key=view_key,
            scope=ViewPreferenceScope.TEAM.value,
            user_id=0,
        )

    def upsert(
        self,
        db: Session,
        *,
        team_id: int,
        user_id: int,
        view_key: str,
        scope: str,
        config: ViewPreferenceConfig,
        actor_id: int,
        name: str | None = None,
        is_default: bool = True,
    ) -> ViewPreference:
        owner_user_id = user_id if scope == ViewPreferenceScope.PERSONAL.value else 0
        serialized_config = config.model_dump_json()
        existing = self.get(
            db,
            team_id=team_id,
            view_key=view_key,
            scope=scope,
            user_id=owner_user_id,
            preference_key="default",
        )

        if existing:
            existing.config_json = serialized_config
            existing.updated_by = actor_id
            existing.name = name
            existing.is_default = 1 if is_default else 0
            db.commit()
            db.refresh(existing)
            return existing

        preference = ViewPreference(
            team_id=team_id,
            user_id=owner_user_id,
            view_key=view_key,
            scope=scope,
            preference_key="default",
            name=name,
            is_default=1 if is_default else 0,
            config_json=serialized_config,
            created_by=actor_id,
            updated_by=actor_id,
        )
        db.add(preference)
        db.commit()
        db.refresh(preference)
        return preference

    def delete(self, db: Session, *, team_id: int, view_key: str, scope: str, user_id: int) -> bool:
        owner_user_id = user_id if scope == ViewPreferenceScope.PERSONAL.value else 0
        preference = self.get(
            db,
            team_id=team_id,
            view_key=view_key,
            scope=scope,
            user_id=owner_user_id,
            preference_key="default",
        )
        if not preference:
            return False
        db.delete(preference)
        db.commit()
        return True

    def list_custom_views(self, db: Session, *, team_id: int, view_key: str, user_id: int) -> list[ViewPreference]:
        return db.query(ViewPreference).filter(
            ViewPreference.team_id == team_id,
            ViewPreference.view_key == view_key,
            ViewPreference.scope == ViewPreferenceScope.PERSONAL.value,
            ViewPreference.user_id == user_id,
            ViewPreference.is_default == 0,
        ).order_by(ViewPreference.sort_order.is_(None), ViewPreference.sort_order.asc(), ViewPreference.id.asc()).all()

    def create_custom_view(
        self,
        db: Session,
        *,
        team_id: int,
        view_key: str,
        user_id: int,
        config: ViewPreferenceConfig,
        actor_id: int,
    ) -> ViewPreference:
        custom_view_count = len(self.list_custom_views(db, team_id=team_id, view_key=view_key, user_id=user_id))
        preference = ViewPreference(
            team_id=team_id,
            user_id=user_id,
            view_key=view_key,
            scope=ViewPreferenceScope.PERSONAL.value,
            preference_key=f"custom:pending:{uuid4().hex}",
            name=f"视图 {custom_view_count + 1}",
            is_default=0,
            config_json=config.model_dump_json(),
            created_by=actor_id,
            updated_by=actor_id,
        )
        db.add(preference)
        db.commit()
        preference.preference_key = f"custom:{preference.id}"
        db.commit()
        db.refresh(preference)
        return preference

    def get_custom_view(
        self,
        db: Session,
        *,
        team_id: int,
        view_key: str,
        user_id: int,
        preference_id: int,
    ) -> Optional[ViewPreference]:
        return db.query(ViewPreference).filter(
            ViewPreference.id == preference_id,
            ViewPreference.team_id == team_id,
            ViewPreference.view_key == view_key,
            ViewPreference.scope == ViewPreferenceScope.PERSONAL.value,
            ViewPreference.user_id == user_id,
            ViewPreference.is_default == 0,
        ).first()

    def update_custom_view(
        self,
        db: Session,
        *,
        team_id: int,
        view_key: str,
        user_id: int,
        preference_id: int,
        actor_id: int,
        name: str | None = None,
        config: ViewPreferenceConfig | None = None,
        sort_order: int | None = None,
    ) -> Optional[ViewPreference]:
        preference = self.get_custom_view(
            db,
            team_id=team_id,
            view_key=view_key,
            user_id=user_id,
            preference_id=preference_id,
        )
        if not preference:
            return None
        if name is not None:
            preference.name = name
        if config is not None:
            preference.config_json = config.model_dump_json()
        if sort_order is not None:
            preference.sort_order = sort_order
        preference.updated_by = actor_id
        db.commit()
        db.refresh(preference)
        return preference

    def delete_custom_view(
        self,
        db: Session,
        *,
        team_id: int,
        view_key: str,
        user_id: int,
        preference_id: int,
    ) -> bool:
        preference = self.get_custom_view(
            db,
            team_id=team_id,
            view_key=view_key,
            user_id=user_id,
            preference_id=preference_id,
        )
        if not preference:
            return False
        db.delete(preference)
        db.commit()
        return True


def parse_config(config_json: str) -> ViewPreferenceConfig:
    return ViewPreferenceConfig(**json.loads(config_json))


view_preference_crud = ViewPreferenceCRUD()
