from app.core.database import SessionLocal
from app.models.customer import Customer
from app.models.user import User


def check_owners():
    db = SessionLocal()
    try:
        print("=" * 60)
        print("检查客户和用户数据")
        print("=" * 60)
        
        print("\n1. 客户表中的 owner_id 分布：")
        customers = db.query(Customer.owner_id).filter(
            Customer.owner_id.isnot(None)
        ).distinct().all()
        
        for (owner_id,) in customers:
            count = db.query(Customer).filter(Customer.owner_id == owner_id).count()
            print(f"   - {owner_id}: {count} 个客户")
        
        print("\n2. 用户表中的 feishu_open_id：")
        users = db.query(User.feishu_open_id, User.name).all()
        for feishu_open_id, name in users[:10]:
            print(f"   - {feishu_open_id}: {name}")
        
        print("\n3. JOIN 查询结果：")
        results = db.query(
            Customer.owner_id,
            User.name
        ).outerjoin(
            User, Customer.owner_id == User.feishu_open_id
        ).filter(
            Customer.owner_id.isnot(None)
        ).distinct().all()
        
        if results:
            for owner_id, user_name in results:
                print(f"   - {owner_id}: {user_name}")
        else:
            print("   （空）JOIN 查询没有返回任何结果")
        
        print("\n4. 检查特定 owner_id 是否存在于用户表：")
        test_owner_ids = ['admin_open_id', 'director_open_id', 'mock_open_id_Harry']
        for test_id in test_owner_ids:
            user = db.query(User).filter(User.feishu_open_id == test_id).first()
            if user:
                print(f"   ✓ {test_id} -> 用户: {user.name}")
            else:
                print(f"   ✗ {test_id} -> 不存在")
        
    finally:
        db.close()


if __name__ == "__main__":
    check_owners()
