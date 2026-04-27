"""
权限服务模块
处理权限相关的业务逻辑，包括缓存管理
"""
from typing import List
from sqlalchemy.orm import Session
from app.core.redis import get_redis_client
from app.models.permission import Permission
from app.models.user_role import UserRole
from app.models.role_permission import RolePermission
import json


class PermissionService:
    """权限服务类"""
    
    def __init__(self):
        self.cache_prefix = "user_permissions"
        self.cache_ttl = 3600  # 1小时
    
    def get_cache_key(self, user_id: int) -> str:
        """生成用户权限缓存键"""
        return f"{self.cache_prefix}:{user_id}"
    
    def clear_user_permissions_cache(self, user_id: int) -> bool:
        """
        清除用户权限缓存
        
        当用户的角色或角色权限发生变更时，应调用此方法清除缓存
        确保下次获取权限时从数据库重新加载最新数据
        
        Args:
            user_id: 用户ID
        
        Returns:
            bool: 是否成功清除缓存
        """
        try:
            redis_client = get_redis_client()
            cache_key = self.get_cache_key(user_id)
            redis_client.delete(cache_key)
            return True
        except Exception as e:
            print(f"清除用户权限缓存失败: {str(e)}")
            return False
    
    def clear_all_permissions_cache(self) -> bool:
        """
        清除所有用户权限缓存
        
        当系统权限结构发生重大变更时使用（慎用）
        例如：权限迁移、角色权限批量调整等
        
        Returns:
            bool: 是否成功清除缓存
        """
        try:
            redis_client = get_redis_client()
            pattern = f"{self.cache_prefix}:*"
            keys = redis_client.keys(pattern)
            if keys:
                redis_client.delete(*keys)
            return True
        except Exception as e:
            print(f"清除所有权限缓存失败: {str(e)}")
            return False
    
    def get_user_permissions_from_db(self, db: Session, user_id: int) -> List[Permission]:
        """
        从数据库获取用户的所有权限（合并去重）
        
        权限合并策略：取并集（Union）
        - 用户拥有其所有角色的权限集合
        - 相同的权限只保留一份
        
        Args:
            db: 数据库会话
            user_id: 用户ID
        
        Returns:
            List[Permission]: 用户的权限列表
        """
        permissions = db.query(Permission).join(
            RolePermission, Permission.id == RolePermission.permission_id
        ).join(
            UserRole, RolePermission.role_id == UserRole.role_id
        ).filter(
            UserRole.user_id == user_id
        ).distinct().all()
        
        return permissions
    
    def get_user_permissions_with_cache(
        self, 
        db: Session, 
        user_id: int,
        use_cache: bool = True
    ) -> tuple[List[Permission], bool]:
        """
        获取用户权限（支持缓存）
        
        Args:
            db: 数据库会话
            user_id: 用户ID
            use_cache: 是否使用缓存
        
        Returns:
            tuple[List[Permission], bool]: (权限列表, 是否来自缓存)
        """
        cached = False
        permissions = None
        
        if use_cache:
            try:
                redis_client = get_redis_client()
                cache_key = self.get_cache_key(user_id)
                cached_data = redis_client.get(cache_key)
                
                if cached_data:
                    from app.schemas.permission import UserPermissionResponse
                    permissions_dict = json.loads(cached_data)
                    cached = True
                    
                    return [
                        Permission(
                            id=p['id'],
                            code=p['code'],
                            name=p['name'],
                            resource=p['resource'],
                            action=p['action'],
                            scope=p.get('scope'),
                            description=p.get('description')
                        )
                        for p in permissions_dict
                    ], True
            except Exception as e:
                print(f"读取权限缓存失败: {str(e)}")
        
        if not permissions:
            permissions = self.get_user_permissions_from_db(db, user_id)
            
            if use_cache:
                try:
                    redis_client = get_redis_client()
                    cache_key = self.get_cache_key(user_id)
                    permissions_dict = [
                        {
                            'id': p.id,
                            'code': p.code,
                            'name': p.name,
                            'resource': p.resource,
                            'action': p.action,
                            'scope': p.scope,
                            'description': p.description
                        }
                        for p in permissions
                    ]
                    redis_client.setex(
                        cache_key,
                        self.cache_ttl,
                        json.dumps(permissions_dict, ensure_ascii=False)
                    )
                except Exception as e:
                    print(f"写入权限缓存失败: {str(e)}")
        
        return permissions, cached
    
    def invalidate_user_cache_on_role_change(self, user_id: int) -> None:
        """
        用户角色变更时清除缓存
        
        Args:
            user_id: 用户ID
        """
        self.clear_user_permissions_cache(user_id)
    
    def invalidate_cache_on_permission_change(self) -> None:
        """
        权限变更时清除所有缓存
        
        当权限本身被修改或删除时，需要清除所有缓存
        """
        self.clear_all_permissions_cache()
    
    def invalidate_cache_on_role_permission_change(self, role_id: int) -> bool:
        """
        角色权限变更时清除相关用户缓存
        
        Args:
            role_id: 角色ID
        
        Returns:
            bool: 是否成功清除缓存
        """
        try:
            redis_client = get_redis_client()
            
            from app.models.user_role import UserRole
            from app.core.database import get_db
            
            db = next(get_db())
            try:
                user_roles = db.query(UserRole).filter(
                    UserRole.role_id == role_id
                ).all()
                
                for user_role in user_roles:
                    self.clear_user_permissions_cache(user_role.user_id)
                
                return True
            finally:
                db.close()
        except Exception as e:
            print(f"清除角色相关用户权限缓存失败: {str(e)}")
            return False


permission_service = PermissionService()
