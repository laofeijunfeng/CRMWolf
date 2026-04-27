from app.core.database import SessionLocal
from app.models.lead import Lead, LeadStatus
from app.models.user import User
from app.models.role import Role
from sqlalchemy.orm import Session


def check_leads_and_user():
    db: Session = SessionLocal()
    try:
        print("=" * 50)
        print("检查线索和用户信息")
        print("=" * 50)
        
        print("\n1. 所有未转化的线索：")
        active_leads = db.query(Lead).filter(
            Lead.status != LeadStatus.CONVERTED
        ).all()
        print(f"   总数：{len(active_leads)}")
        for lead in active_leads:
            print(f"   - ID: {lead.id}, 名称: {lead.lead_name}, 负责人: {lead.owner_id}, 状态: {lead.status}")
        
        print("\n2. 当前用户信息（token中用户ID=5）：")
        user = db.query(User).filter(User.id == 5).first()
        if user:
            print(f"   用户ID: {user.id}")
            print(f"   飞书Open ID: {user.feishu_open_id}")
            print(f"   姓名: {user.name}")
            
            print("\n3. 用户角色：")
            roles = db.query(Role).join(User.role).filter(User.id == user.id).all()
            for role in roles:
                print(f"   - {role.name} ({role.code})")
            
            print("\n4. 该用户应该能看到的线索：")
            user_leads = db.query(Lead).filter(
                Lead.status != LeadStatus.CONVERTED,
                Lead.owner_id == user.feishu_open_id
            ).all()
            print(f"   总数：{len(user_leads)}")
            for lead in user_leads:
                print(f"   - ID: {lead.id}, 名称: {lead.lead_name}, 状态: {lead.status}")
        else:
            print("   用户不存在")
        
        print("\n5. 公海线索（owner_id为空）：")
        public_leads = db.query(Lead).filter(
            Lead.status != LeadStatus.CONVERTED,
            Lead.owner_id.is_(None)
        ).all()
        print(f"   总数：{len(public_leads)}")
        for lead in public_leads:
            print(f"   - ID: {lead.id}, 名称: {lead.lead_name}, 状态: {lead.status}")
        
        print("\n" + "=" * 50)
        
    except Exception as e:
        print(f"检查失败: {e}")
    finally:
        db.close()


if __name__ == "__main__":
    check_leads_and_user()
