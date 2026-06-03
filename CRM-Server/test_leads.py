#!/usr/bin/env python3
import sys
sys.path.insert(0, '/Users/eddie/Code/CRMWolf/CRM-Server')

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

DATABASE_URL = "mysql+pymysql://root:N0k2x4gzjnbbH3zEmDPW@localhost:3306/crm_db"
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)

db = SessionLocal()

# Test get_user_current_team
from app.models.team import UserTeam
user_team = db.query(UserTeam).filter(
    UserTeam.user_id == 2,
    UserTeam.current_team == True
).first()

print(f"User 2 current team: {user_team}")
if user_team:
    print(f"  team_id: {user_team.team_id}")

# Test leads query
from app.models.lead import Lead, LeadStatus
if user_team:
    query = db.query(Lead).filter(Lead.team_id == user_team.team_id)
    query = query.filter(Lead.status != LeadStatus.CONVERTED)
    total = query.count()
    print(f"Leads count for team_id={user_team.team_id}: {total}")

    # Check if team_id column exists
    try:
        result = db.execute("SELECT id, team_id FROM crm_leads LIMIT 5")
        rows = result.fetchall()
        print("Sample leads:")
        for row in rows:
            print(f"  id={row[0]}, team_id={row[1]}")
    except Exception as e:
        print(f"Error checking leads: {e}")

db.close()