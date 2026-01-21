#!/usr/bin/env python3
"""
Run Supabase migration to add AI columns.
Uses the Supabase service role key to execute SQL.
"""

import os
from dotenv import load_dotenv
from supabase import create_client

# Load env from datacollection folder
load_dotenv('/Users/flyn/dataCollection/datacollection/.env')

SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_KEY = os.getenv('SUPABASE_KEY')

if not SUPABASE_URL or not SUPABASE_KEY:
    print("Error: Missing SUPABASE_URL or SUPABASE_KEY")
    exit(1)

# Read migration SQL
migration_path = os.path.join(os.path.dirname(__file__), 'migrations', '001_add_ai_columns.sql')
with open(migration_path, 'r') as f:
    migration_sql = f.read()

# Split into individual statements (skip comments and empty lines)
statements = []
current_stmt = []
for line in migration_sql.split('\n'):
    line = line.strip()
    if line.startswith('--') or not line:
        continue
    current_stmt.append(line)
    if line.endswith(';'):
        statements.append(' '.join(current_stmt))
        current_stmt = []

print(f"Found {len(statements)} SQL statements to execute")
print(f"Connecting to: {SUPABASE_URL}")

# Create client
client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Execute each statement using rpc
# Note: We need to use a custom RPC function or direct SQL execution
# For Supabase, we'll use the postgrest-py raw execute method

# Alternative: use psycopg2 directly with the connection string
try:
    import psycopg2

    # Construct connection string from Supabase URL
    # Format: postgresql://postgres:[PASSWORD]@db.[PROJECT_REF].supabase.co:5432/postgres
    project_ref = SUPABASE_URL.split('//')[1].split('.')[0]

    # For Supabase, we need the database password (not the API key)
    # The service role key is a JWT, not a database password
    # We'll need to use a different approach

    print("Note: Direct database connection requires the database password.")
    print("Using Supabase REST API instead...")
    raise ImportError("Switching to REST API approach")

except ImportError:
    # Use requests to call the SQL Editor API
    import requests

    # Supabase doesn't have a public SQL execution API
    # We need to create an RPC function or use the dashboard

    print("\nThe migration SQL needs to be run manually in Supabase Dashboard.")
    print("Go to: https://supabase.com/dashboard/project/cxcgeumhfjvnuibxnbob/sql")
    print("\nSQL to run:")
    print("-" * 60)
    print(migration_sql)
    print("-" * 60)

    # Try to verify if columns already exist by querying the table
    print("\nChecking if columns already exist...")
    try:
        result = client.table('worcester_data_collection').select('ai_enriched').limit(1).execute()
        print("SUCCESS: ai_enriched column exists! Migration may have already been run.")
    except Exception as e:
        if 'ai_enriched' in str(e):
            print("Column 'ai_enriched' does not exist yet. Please run the migration SQL above.")
        else:
            print(f"Check failed: {e}")
