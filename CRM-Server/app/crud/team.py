import json
import random
import string
from sqlalchemy.orm import Session
from typing import Optional, List
from app.models.team import Team, UserTeam
from app.schemas.team import TeamCreate, TeamUpdate
from app.models.user import User


class TeamCRUD:
    def generate_invite_code(self, length: int = 8) -> str:
        """生成随机邀请码"""
        chars = string.ascii_uppercase + string.digits
        return ''.join(random.choices(chars, k=length))

    def get_by_id(self, db: Session, team_id: int) -> Optional[Team]:
        return db.query(Team).filter(Team.id == team_id).first()

    def get_by_code(self, db: Session, code: str) -> Optional[Team]:
        return db.query(Team).filter(Team.code == code).first()

    def get_multi(self, db: Session, skip: int = 0, limit: int = 100) -> List[Team]:
        return db.query(Team).offset(skip).limit(limit).all()

    def get_all_teams(self, db: Session) -> List[Team]:
        """获取所有团队列表"""
        return db.query(Team).all()

    def create(self, db: Session, obj_in: TeamCreate, owner_id: int) -> Team:
        """创建团队，自动生成邀请码，并复制系统默认权重配置"""
        invite_code = self.generate_invite_code()
        db_obj = Team(
            name=obj_in.name,
            code=invite_code,
            owner_id=owner_id
        )
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)

        # 自动复制系统默认权重配置到新团队
        from app.crud.score_weight import score_weight_crud
        try:
            score_weight_crud.create_team_weights_from_system(
                db, db_obj.id, None, str(owner_id)  # 复制所有模块的权重配置
            )
        except Exception as e:
            # 权重配置复制失败不影响团队创建
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"复制权重配置到新团队失败: team_id={db_obj.id}, error={str(e)}")

        return db_obj

    def update(self, db: Session, db_obj: Team, obj_in: TeamUpdate) -> Team:
        update_data = obj_in.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(db_obj, field, value)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def delete(self, db: Session, team_id: int) -> Optional[Team]:
        obj = db.query(Team).filter(Team.id == team_id).first()
        if obj:
            db.delete(obj)
            db.commit()
        return obj

    def regenerate_code(self, db: Session, team_id: int) -> str:
        """重新生成邀请码"""
        team = self.get_by_id(db, team_id)
        if team:
            team.code = self.generate_invite_code()
            db.commit()
            db.refresh(team)
            return team.code
        return ""

    def get_members(self, db: Session, team_id: int) -> List[User]:
        """获取团队成员列表"""
        return db.query(User).join(
            UserTeam, User.id == UserTeam.user_id
        ).filter(UserTeam.team_id == team_id).all()

    def get_member_info(self, db: Session, team_id: int) -> List[dict]:
        """获取团队成员详细信息（包含角色）"""
        from sqlalchemy import text
        # MySQL 兼容语法（不支持 PostgreSQL 的 FILTER 和 ::json）
        result = db.execute(text("""
            SELECT u.id, u.name, u.email, u.avatar_url, ut.current_team, ut.joined_at,
                   IFNULL(
                       JSON_ARRAYAGG(
                           CASE WHEN r.id IS NOT NULL
                               THEN JSON_OBJECT('id', r.id, 'name', r.name, 'code', r.code)
                               ELSE NULL
                           END
                       ),
                       JSON_ARRAY()
                   ) as roles
            FROM users u
            JOIN user_teams ut ON u.id = ut.user_id
            LEFT JOIN user_roles ur ON u.id = ur.user_id AND ur.team_id = :team_id
            LEFT JOIN roles r ON ur.role_id = r.id
            WHERE ut.team_id = :team_id
            GROUP BY u.id, u.name, u.email, u.avatar_url, ut.current_team, ut.joined_at
            ORDER BY ut.joined_at
        """), {"team_id": team_id})
        # 处理 roles 数组中的 NULL 值
        members = []
        for row in result:
            m = dict(row._mapping)
            # 移除 roles 数组中的 NULL 元素
            if m['roles']:
                try:
                    roles_list = json.loads(m['roles']) if isinstance(m['roles'], str) else m['roles']
                    m['roles'] = [r for r in roles_list if r is not None]
                except:
                    m['roles'] = []
            else:
                m['roles'] = []
            members.append(m)
        return members

    def add_member(self, db: Session, team_id: int, user_id: int, set_current: bool = True) -> UserTeam:
        """添加成员到团队"""
        # 检查用户是否已加入该团队
        existing = db.query(UserTeam).filter(
            UserTeam.user_id == user_id,
            UserTeam.team_id == team_id
        ).first()
        if existing:
            return existing

        # 如果设置为当前团队且用户没有其他团队，则设为当前
        if set_current:
            user_teams_count = db.query(UserTeam).filter(
                UserTeam.user_id == user_id
            ).count()
            is_current = user_teams_count == 0
        else:
            is_current = False

        user_team = UserTeam(
            user_id=user_id,
            team_id=team_id,
            current_team=is_current
        )
        db.add(user_team)
        db.commit()
        db.refresh(user_team)
        return user_team

    def remove_member(self, db: Session, team_id: int, user_id: int) -> bool:
        """移除团队成员（同步删除角色关系）"""
        from app.crud.role import role_crud

        # 先删除用户在该团队的所有角色
        role_crud.remove_all_user_roles_in_team(db, user_id, team_id)

        # 再删除用户-团队关联
        user_team = db.query(UserTeam).filter(
            UserTeam.user_id == user_id,
            UserTeam.team_id == team_id
        ).first()
        if user_team:
            db.delete(user_team)
            db.commit()
            return True
        return False

    def set_current_team(self, db: Session, user_id: int, team_id: int) -> bool:
        """设置用户的当前活跃团队"""
        # 验证用户属于该团队
        user_team = db.query(UserTeam).filter(
            UserTeam.user_id == user_id,
            UserTeam.team_id == team_id
        ).first()
        if not user_team:
            return False

        # 清除其他团队的 current_team 标记
        db.query(UserTeam).filter(
            UserTeam.user_id == user_id
        ).update({"current_team": False})

        # 设置当前团队
        user_team.current_team = True
        db.commit()
        return True

    def get_user_teams(self, db: Session, user_id: int) -> List[Team]:
        """获取用户所属的所有团队"""
        return db.query(Team).join(
            UserTeam, Team.id == UserTeam.team_id
        ).filter(UserTeam.user_id == user_id).all()

    def get_user_current_team(self, db: Session, user_id: int) -> Optional[int]:
        """获取用户当前活跃团队ID"""
        user_team = db.query(UserTeam).filter(
            UserTeam.user_id == user_id,
            UserTeam.current_team == True
        ).first()
        return user_team.team_id if user_team else None

    def is_member(self, db: Session, team_id: int, user_id: int) -> bool:
        """检查用户是否为团队成员"""
        return db.query(UserTeam).filter(
            UserTeam.team_id == team_id,
            UserTeam.user_id == user_id
        ).first() is not None

    def is_owner(self, db: Session, team_id: int, user_id: int) -> bool:
        """检查用户是否为团队创建者"""
        team = self.get_by_id(db, team_id)
        return team and team.owner_id == user_id


class UserTeamCRUD:
    def get_by_user_and_team(self, db: Session, user_id: int, team_id: int) -> Optional[UserTeam]:
        return db.query(UserTeam).filter(
            UserTeam.user_id == user_id,
            UserTeam.team_id == team_id
        ).first()

    def get_user_current_team(self, db: Session, user_id: int) -> Optional[UserTeam]:
        return db.query(UserTeam).filter(
            UserTeam.user_id == user_id,
            UserTeam.current_team == True
        ).first()

    def get_user_teams(self, db: Session, user_id: int) -> List[UserTeam]:
        return db.query(UserTeam).filter(UserTeam.user_id == user_id).all()


team_crud = TeamCRUD()
user_team_crud = UserTeamCRUD()