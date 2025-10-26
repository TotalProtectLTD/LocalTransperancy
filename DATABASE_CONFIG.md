# Database Configuration - Local Transparency

## Database Details

- **Database Name**: `local_transparency`
- **User**: `transparency_user`
- **Password**: `transparency_pass_2025`
- **Host**: `localhost`
- **Port**: `5432`
- **PostgreSQL Version**: 18.0 (Homebrew)

## Connection String

```
postgresql://transparency_user:transparency_pass_2025@localhost:5432/local_transparency
```

## Environment Variables

```bash
# Add to .env file (DO NOT COMMIT TO GIT!)
DB_HOST=localhost
DB_PORT=5432
DB_NAME=local_transparency
DB_USER=transparency_user
DB_PASSWORD=transparency_pass_2025
```

## Quick Connection Test

```bash
# Test connection
psql -U transparency_user -d local_transparency -h localhost

# Test with Python
python3 -c "
import psycopg2
conn = psycopg2.connect(
    host='localhost',
    database='local_transparency',
    user='transparency_user',
    password='transparency_pass_2025',
    port=5432
)
print('✅ Database connection successful!')
conn.close()
"
```

## Database Location

- **Data Directory**: `/opt/homebrew/var/postgresql@18/` (Apple Silicon with Homebrew)
- **Config Files**: `/opt/homebrew/var/postgresql@18/postgresql.conf`
- **Log Files**: `/opt/homebrew/var/postgresql@18/log/`

## Homebrew Commands

```bash
# Start PostgreSQL
brew services start postgresql@18

# Stop PostgreSQL
brew services stop postgresql@18

# Restart PostgreSQL
brew services restart postgresql@18

# Check status
brew services list | grep postgresql

# Check if running
pg_isready
```

## Backup Location

```bash
# Create backup (using Homebrew PostgreSQL)
pg_dump -U transparency_user local_transparency > backup_$(date +%Y%m%d).sql

# Restore backup
psql -U transparency_user local_transparency < backup_20251025.sql

# Backup with compression
pg_dump -U transparency_user local_transparency | gzip > backup_$(date +%Y%m%d).sql.gz

# Restore compressed backup
gunzip -c backup_20251025.sql.gz | psql -U transparency_user local_transparency
```

---

**Created**: October 2025  
**Status**: ✅ Database ready for use
