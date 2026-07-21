from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from app.models.oauth import OAuthProviderConfig, UserOAuthAccount


class OAuthProviderConfigCRUD:
    def get(self, db: Session, team_id: int, provider: str) -> Optional[OAuthProviderConfig]:
        return db.query(OAuthProviderConfig).filter(
            OAuthProviderConfig.team_id == team_id,
            OAuthProviderConfig.provider == provider,
        ).first()

    def upsert_feishu(
        self,
        db: Session,
        team_id: int,
        app_id: str,
        redirect_uri: str,
        enabled: bool,
        app_secret: Optional[str] = None,
    ) -> OAuthProviderConfig:
        config = self.get(db, team_id, "feishu")
        if config is None:
            config = OAuthProviderConfig(
                team_id=team_id,
                provider="feishu",
                app_id=app_id,
                redirect_uri=redirect_uri,
                enabled=enabled,
            )
            db.add(config)

        config.app_id = app_id
        config.redirect_uri = redirect_uri
        config.enabled = enabled
        if app_secret:
            config.app_secret_encrypted = OAuthProviderConfig.encrypt_secret(app_secret)

        db.commit()
        db.refresh(config)
        return config

    def get_secret(self, config: OAuthProviderConfig) -> Optional[str]:
        if not config.app_secret_encrypted:
            return None
        return OAuthProviderConfig.decrypt_secret(config.app_secret_encrypted)


class UserOAuthAccountCRUD:
    def get_by_open_id(
        self,
        db: Session,
        team_id: int,
        provider: str,
        open_id: str,
    ) -> Optional[UserOAuthAccount]:
        return db.query(UserOAuthAccount).filter(
            UserOAuthAccount.team_id == team_id,
            UserOAuthAccount.provider == provider,
            UserOAuthAccount.open_id == open_id,
        ).first()

    def get_by_user(
        self,
        db: Session,
        team_id: int,
        provider: str,
        user_id: int,
    ) -> Optional[UserOAuthAccount]:
        return db.query(UserOAuthAccount).filter(
            UserOAuthAccount.team_id == team_id,
            UserOAuthAccount.provider == provider,
            UserOAuthAccount.user_id == user_id,
        ).first()

    def upsert(
        self,
        db: Session,
        team_id: int,
        provider: str,
        user_id: int,
        profile: Dict[str, Any],
    ) -> UserOAuthAccount:
        account = self.get_by_user(db, team_id, provider, user_id)
        if account is None and profile.get("open_id"):
            account = self.get_by_open_id(db, team_id, provider, profile["open_id"])
        if account is None:
            account = UserOAuthAccount(team_id=team_id, provider=provider, user_id=user_id)
            db.add(account)

        account.user_id = user_id
        account.provider_user_id = profile.get("user_id")
        account.open_id = profile.get("open_id")
        account.union_id = profile.get("union_id")
        account.tenant_key = profile.get("tenant_key")
        account.email = profile.get("email")
        account.mobile = profile.get("mobile")
        account.name = profile.get("name")
        account.avatar_url = profile.get("avatar_url")
        account.raw_profile = profile.get("raw")

        db.commit()
        db.refresh(account)
        return account

    def delete_by_user(self, db: Session, team_id: int, provider: str, user_id: int) -> bool:
        account = self.get_by_user(db, team_id, provider, user_id)
        if not account:
            return False
        db.delete(account)
        db.commit()
        return True


oauth_provider_config_crud = OAuthProviderConfigCRUD()
user_oauth_account_crud = UserOAuthAccountCRUD()
