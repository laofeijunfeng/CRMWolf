#!/bin/bash
set -e

echo "=== CRMWolf Backend Startup ==="

# Set PYTHONPATH for module imports
export PYTHONPATH=/app

# Read secrets from files if available
if [ -f /run/secrets/db_password ]; then
    export DB_PASSWORD=$(cat /run/secrets/db_password)
    echo "Loaded DB_PASSWORD from secrets"
fi
if [ -f /run/secrets/secret_key ]; then
    export SECRET_KEY=$(cat /run/secrets/secret_key)
fi

# Function to wait for MySQL
wait_for_mysql() {
    echo "Waiting for MySQL to be ready..."
    max_attempts=30
    attempt=0

    while [ $attempt -lt $max_attempts ]; do
        DB_HOST=${DB_HOST:-mysql}
        DB_PORT=${DB_PORT:-3306}
        DB_USER=${DB_USER:-root}

        if python -c "import pymysql; pymysql.connect(host='$DB_HOST', port=int('$DB_PORT'), user='$DB_USER', password='$DB_PASSWORD')" 2>/dev/null; then
            echo "MySQL is ready!"
            return 0
        fi

        attempt=$((attempt + 1))
        echo "MySQL not ready yet, attempt $attempt/$max_attempts"
        sleep 2
    done

    echo "ERROR: MySQL not ready after $max_attempts attempts"
    return 1
}

# Function to check if tables exist
check_tables_exist() {
    python -c "
import sys
sys.path.insert(0, '/app')
from sqlalchemy import create_engine, text
from app.core.config import get_settings

settings = get_settings()
engine = create_engine(settings.DATABASE_URL)

with engine.connect() as conn:
    result = conn.execute(text('SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = DATABASE() AND table_name = \"users\"'))
    count = result.fetchone()[0]
    if count > 0:
        print('Tables exist')
        sys.exit(0)
    else:
        print('No tables found')
        sys.exit(1)
" 2>/dev/null
    return $?
}

# Function to check if data initialized
check_data_initialized() {
    python -c "
import sys
sys.path.insert(0, '/app')
from sqlalchemy import create_engine, text
from app.core.config import get_settings

settings = get_settings()
engine = create_engine(settings.DATABASE_URL)

with engine.connect() as conn:
    result = conn.execute(text('SELECT COUNT(*) FROM roles'))
    count = result.fetchone()[0]
    if count > 0:
        print('Data already initialized')
        sys.exit(0)
    else:
        print('Data needs initialization')
        sys.exit(1)
" 2>/dev/null
    return $?
}

# Function to create all tables
create_tables() {
    python -c "
import sys
sys.path.insert(0, '/app')
from app.core.database import Base, engine

# Import all models to ensure they are registered
import app.models

Base.metadata.create_all(bind=engine)
print('All tables created successfully')
"
}

# Main startup sequence
echo "Step 1: Waiting for MySQL..."
wait_for_mysql

echo "Step 2: Checking if tables exist..."
if ! check_tables_exist; then
    echo "Creating all tables..."
    create_tables
    echo "Stamping alembic to latest version..."
    python -m alembic stamp head
fi

echo "Step 3: Running any pending migrations..."
python -m alembic upgrade head

echo "Step 4: Checking if data needs initialization..."
if ! check_data_initialized; then
    echo "Initializing roles and permissions (first time)..."
    python scripts/init_db.py
fi

echo "Step 4b: Ensuring all role permissions are synced..."
python -c "
import sys
sys.path.insert(0, '/app')
from app.services.init_service import init_roles_permissions
init_roles_permissions()
"

echo "Step 5: Starting application..."
exec python -m uvicorn app.main:app --host 0.0.0.0 --port 8000