from app.core.database import SessionLocal
from app.models.lead import Lead, LeadStatus
from app.models.customer import Customer


def fix_converted_leads_status():
    db = SessionLocal()
    try:
        print("开始修复历史数据...")
        
        customers_with_lead_source = db.query(Customer).filter(
            Customer.source_lead_id.isnot(None)
        ).all()
        
        print(f"找到 {len(customers_with_lead_source)} 个已转化的客户")
        
        updated_count = 0
        skipped_count = 0
        
        for customer in customers_with_lead_source:
            lead = db.query(Lead).filter(Lead.id == customer.source_lead_id).first()
            
            if lead:
                if lead.status != LeadStatus.CONVERTED:
                    lead.status = LeadStatus.CONVERTED
                    lead.version += 1
                    updated_count += 1
                    print(f"更新线索 {lead.id} ({lead.lead_name}) 状态为已转化")
                else:
                    skipped_count += 1
                    print(f"线索 {lead.id} ({lead.lead_name}) 状态已是已转化，跳过")
            else:
                print(f"警告：客户 {customer.account_name} 关联的线索 {customer.source_lead_id} 不存在")
        
        db.commit()
        
        print(f"\n修复完成！")
        print(f"共更新 {updated_count} 条线索状态")
        print(f"跳过 {skipped_count} 条已是转化状态的线索")
        
    except Exception as e:
        print(f"修复失败: {e}")
        db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    fix_converted_leads_status()
