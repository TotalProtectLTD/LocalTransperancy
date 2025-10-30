#!/usr/bin/env python3
"""
Database Backup Script - Local Transparency

Creates a PostgreSQL database backup and saves it to db_backups/ folder.
"""

import psycopg2
import subprocess
import os
import sys
from pathlib import Path
from datetime import datetime

# Database configuration (same as setup_database.py)
DB_CONFIG = {
    'host': 'localhost',
    'database': 'local_transparency',
    'user': 'transparency_user',
    'password': 'transparency_pass_2025',
    'port': 5432
}

# Backup directory
BACKUP_DIR = Path(__file__).parent / 'db_backups'


def create_backup_directory():
    """Create backup directory if it doesn't exist."""
    BACKUP_DIR.mkdir(exist_ok=True)
    print(f"✅ Backup directory: {BACKUP_DIR}")


def verify_postgresql_installed():
    """Verify pg_dump is installed."""
    try:
        result = subprocess.run(
            ['pg_dump', '--version'],
            capture_output=True,
            text=True,
            check=True
        )
        print(f"✅ PostgreSQL tools found: {result.stdout.strip()}")
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("❌ Error: pg_dump not found. Please install PostgreSQL client tools.")
        print("   macOS: brew install postgresql")
        print("   Ubuntu: sudo apt-get install postgresql-client")
        print("   Windows: Install PostgreSQL from https://www.postgresql.org/download/")
        return False


def verify_connection():
    """Verify database connection before backup."""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        cursor.execute("SELECT version();")
        version = cursor.fetchone()[0]
        print(f"✅ Database connection verified")
        print(f"   Server: {DB_CONFIG['host']}:{DB_CONFIG['port']}")
        print(f"   Database: {DB_CONFIG['database']}")
        cursor.close()
        conn.close()
        return True
    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        print(f"   Check your database configuration in {__file__}")
        return False


def create_backup(filename: str = None):
    """
    Create a PostgreSQL database backup.
    
    Args:
        filename: Optional custom filename. If None, uses timestamp.
    
    Returns:
        Path to backup file, or None if failed.
    """
    # Generate filename with timestamp if not provided
    if filename is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"backup_{timestamp}.sql"
    
    # Ensure filename has .sql extension
    if not filename.endswith('.sql'):
        filename += '.sql'
    
    backup_path = BACKUP_DIR / filename
    
    # Check if file already exists
    if backup_path.exists():
        response = input(f"⚠️  File {filename} already exists. Overwrite? (y/N): ")
        if response.lower() != 'y':
            print("❌ Backup cancelled")
            return None
    
    # Build pg_dump command
    pg_dump_cmd = [
        'pg_dump',
        '-h', DB_CONFIG['host'],
        '-p', str(DB_CONFIG['port']),
        '-U', DB_CONFIG['user'],
        '-d', DB_CONFIG['database'],
        '-F', 'p',  # Plain text format
        '-f', str(backup_path),
        '--verbose'  # Show progress
    ]
    
    # Set PGPASSWORD environment variable
    env = os.environ.copy()
    env['PGPASSWORD'] = DB_CONFIG['password']
    
    print(f"\n🔄 Creating backup: {filename}")
    print(f"   Destination: {backup_path}")
    
    try:
        result = subprocess.run(
            pg_dump_cmd,
            env=env,
            capture_output=False,  # Show output in real-time
            check=True
        )
        
        # Verify backup file was created and has size > 0
        if backup_path.exists() and backup_path.stat().st_size > 0:
            size_mb = backup_path.stat().st_size / (1024 * 1024)
            print(f"\n✅ Backup created successfully!")
            print(f"   File: {filename}")
            print(f"   Size: {size_mb:.2f} MB")
            print(f"   Path: {backup_path}")
            return backup_path
        else:
            print(f"\n❌ Backup file is empty or doesn't exist")
            return None
            
    except subprocess.CalledProcessError as e:
        print(f"\n❌ Backup failed with error code {e.returncode}")
        return None
    except Exception as e:
        print(f"\n❌ Unexpected error during backup: {e}")
        return None


def list_backups():
    """List all backup files in db_backups/."""
    backups = sorted(
        BACKUP_DIR.glob('backup_*.sql'),
        key=lambda p: p.stat().st_mtime,
        reverse=True
    )
    
    if not backups:
        print("📋 No backups found in db_backups/")
        return []
    
    print(f"\n📋 Found {len(backups)} backup(s):")
    for i, backup in enumerate(backups, 1):
        size_mb = backup.stat().st_size / (1024 * 1024)
        mtime = datetime.fromtimestamp(backup.stat().st_mtime)
        print(f"   {i}. {backup.name} ({size_mb:.2f} MB, {mtime.strftime('%Y-%m-%d %H:%M:%S')})")
    
    return backups


def main():
    """Main function."""
    print("=" * 60)
    print("DATABASE BACKUP - Local Transparency")
    print("=" * 60)
    
    # Create backup directory
    create_backup_directory()
    
    # Verify prerequisites
    if not verify_postgresql_installed():
        sys.exit(1)
    
    if not verify_connection():
        sys.exit(1)
    
    # Parse command line arguments
    if len(sys.argv) > 1:
        if sys.argv[1] == '--list':
            list_backups()
            return
        elif sys.argv[1] == '--help':
            print("\nUsage:")
            print("  python3 backup_database.py              # Create backup with timestamp")
            print("  python3 backup_database.py <filename>   # Create backup with custom name")
            print("  python3 backup_database.py --list       # List all backups")
            print("  python3 backup_database.py --help       # Show this help")
            return
        else:
            # Custom filename provided
            filename = sys.argv[1]
            backup_path = create_backup(filename)
    else:
        # Default: timestamp-based filename
        backup_path = create_backup()
    
    if backup_path:
        print("\n💡 Tips:")
        print(f"   • List backups: python3 backup_database.py --list")
        print(f"   • Restore backup: psql -U {DB_CONFIG['user']} -d {DB_CONFIG['database']} < {backup_path}")
        print("\n" + "=" * 60)
    else:
        print("\n❌ Backup failed. Please check errors above.")
        sys.exit(1)


if __name__ == "__main__":
    main()
