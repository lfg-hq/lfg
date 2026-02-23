#!/bin/bash
# PostgreSQL Database Provisioning Script
# Server: 135.181.37.208:5433
# Admin: lfg_admin

PG_HOST="135.181.37.208"
PG_PORT="5433"
PG_ADMIN="lfg_admin"
PG_PASS="LFG_t3st_2026!"

export PGPASSWORD="$PG_PASS"

usage() {
    echo "Usage: $0 <command> <db_name> [db_user] [db_password]"
    echo ""
    echo "Commands:"
    echo "  create  <db_name> [db_user] [db_password]  - Create a database and optional dedicated user"
    echo "  drop    <db_name>                           - Drop a database"
    echo "  list                                        - List all databases"
    echo "  test                                        - Run provisioning self-test"
    echo ""
    echo "Examples:"
    echo "  $0 create myapp_db"
    echo "  $0 create myapp_db myapp_user s3cretPass"
    echo "  $0 drop myapp_db"
    echo "  $0 list"
}

run_sql() {
    psql -h "$PG_HOST" -p "$PG_PORT" -U "$PG_ADMIN" -d postgres -tAc "$1" 2>&1
}

create_db() {
    local db_name="$1"
    local db_user="$2"
    local db_pass="$3"

    echo "Creating database: $db_name"
    run_sql "CREATE DATABASE $db_name;"
    if [ $? -ne 0 ]; then
        echo "FAILED to create database $db_name"
        return 1
    fi
    echo "  Database '$db_name' created."

    if [ -n "$db_user" ]; then
        echo "Creating user: $db_user"
        run_sql "CREATE ROLE $db_user WITH LOGIN PASSWORD '$db_pass';"
        run_sql "GRANT ALL PRIVILEGES ON DATABASE $db_name TO $db_user;"
        run_sql "ALTER DATABASE $db_name OWNER TO $db_user;"
        PGPASSWORD="$PG_PASS" psql -h "$PG_HOST" -p "$PG_PORT" -U "$PG_ADMIN" -d "$db_name" -tAc "GRANT ALL ON SCHEMA public TO $db_user;" 2>&1
        echo "  User '$db_user' created and granted access to '$db_name'."
    fi

    echo ""
    echo "Connection string:"
    if [ -n "$db_user" ]; then
        echo "  postgresql://$db_user:$db_pass@$PG_HOST:$PG_PORT/$db_name"
    else
        echo "  postgresql://$PG_ADMIN:$PG_PASS@$PG_HOST:$PG_PORT/$db_name"
    fi
}

drop_db() {
    local db_name="$1"
    echo "Dropping database: $db_name"
    run_sql "DROP DATABASE IF EXISTS $db_name;"
    echo "  Done."
}

list_dbs() {
    echo "Databases on $PG_HOST:$PG_PORT"
    echo "---"
    psql -h "$PG_HOST" -p "$PG_PORT" -U "$PG_ADMIN" -d postgres -c "\l" 2>&1
}

run_test() {
    local test_db="__provision_test_$(date +%s)"
    local test_user="__test_user_$$"
    local test_pass="testpass123"
    local failed=0

    echo "=== Provisioning Self-Test ==="
    echo ""

    # Test 1: Connection
    echo "[1/5] Testing connection..."
    result=$(run_sql "SELECT 1;")
    if [ "$result" = "1" ]; then
        echo "  PASS - Connected to PostgreSQL"
    else
        echo "  FAIL - Cannot connect: $result"
        return 1
    fi

    # Test 2: Create database
    echo "[2/5] Creating test database: $test_db"
    result=$(run_sql "CREATE DATABASE $test_db;")
    if echo "$result" | grep -qi "error"; then
        echo "  FAIL - $result"
        failed=1
    else
        echo "  PASS - Database created"
    fi

    # Test 3: Create user and grant access
    echo "[3/5] Creating test user: $test_user"
    run_sql "CREATE ROLE $test_user WITH LOGIN PASSWORD '$test_pass';"
    run_sql "GRANT ALL PRIVILEGES ON DATABASE $test_db TO $test_user;"
    run_sql "ALTER DATABASE $test_db OWNER TO $test_user;"
    PGPASSWORD="$PG_PASS" psql -h "$PG_HOST" -p "$PG_PORT" -U "$PG_ADMIN" -d "$test_db" -tAc "GRANT ALL ON SCHEMA public TO $test_user;" > /dev/null 2>&1
    PGPASSWORD="$test_pass" psql -h "$PG_HOST" -p "$PG_PORT" -U "$test_user" -d "$test_db" -tAc "SELECT current_user;" 2>&1 | grep -q "$test_user"
    if [ $? -eq 0 ]; then
        echo "  PASS - User can connect to database"
    else
        echo "  FAIL - User cannot connect"
        failed=1
    fi

    # Test 4: Write and read data
    echo "[4/5] Testing read/write..."
    result=$(PGPASSWORD="$test_pass" psql -h "$PG_HOST" -p "$PG_PORT" -U "$test_user" -d "$test_db" -tAc "
        CREATE TABLE test_table (id serial, name text);
        INSERT INTO test_table (name) VALUES ('hello');
        SELECT name FROM test_table LIMIT 1;
    ")
    if [ "$result" = "hello" ]; then
        echo "  PASS - Read/write works"
    else
        echo "  FAIL - Read/write failed: $result"
        failed=1
    fi

    # Test 5: Cleanup
    echo "[5/5] Cleaning up..."
    export PGPASSWORD="$PG_PASS"
    run_sql "DROP DATABASE IF EXISTS $test_db;"
    run_sql "DROP ROLE IF EXISTS $test_user;"
    echo "  PASS - Cleanup done"

    echo ""
    if [ $failed -eq 0 ]; then
        echo "=== ALL TESTS PASSED ==="
    else
        echo "=== SOME TESTS FAILED ==="
        return 1
    fi
}

# Main
case "${1:-}" in
    create)
        [ -z "$2" ] && { echo "Error: db_name required"; usage; exit 1; }
        create_db "$2" "$3" "$4"
        ;;
    drop)
        [ -z "$2" ] && { echo "Error: db_name required"; usage; exit 1; }
        drop_db "$2"
        ;;
    list)
        list_dbs
        ;;
    test)
        run_test
        ;;
    *)
        usage
        ;;
esac
