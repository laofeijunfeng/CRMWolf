#!/usr/bin/env python3
import sys
sys.path.insert(0, '/Users/eddie/Code/CRMWolf/CRM-Server')

from sqlalchemy import create_engine, text

DATABASE_URL = "mysql+pymysql://root:N0k2x4gzjnbbH3zEmDPW@localhost:3306/crm_db"
engine = create_engine(DATABASE_URL)

with engine.connect() as conn:
    result = conn.execute(text("SELECT * FROM user_teams WHERE user_id = 2"))
    rows = result.fetchall()
    print("User 2 teams:")
    if rows:
        for row in rows:
            print(f"  id={row[0]}, user_id={row[1]}, team_id={row[2]}, current_team={row[3]}")
    else:
        print("  No teams found!")