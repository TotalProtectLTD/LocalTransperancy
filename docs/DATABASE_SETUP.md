# PostgreSQL Database Setup - Local Transparency

This guide covers PostgreSQL installation and setup for the Local Transparency project.

## 📋 Requirements

- **PostgreSQL**: 12.0 or higher (recommended: 18)
- **psycopg2-binary**: Python adapter for PostgreSQL (included in requirements.txt)

## 🚀 Quick Install

### macOS

#### Option 1: Using Homebrew (Recommended)

```bash
# Install PostgreSQL 18
brew install postgresql@18

# Start PostgreSQL service
brew services start postgresql@18

# Verify installation
psql --version
```

#### Option 2: Using Postgres.app

1. Download from [postgresapp.com](https://postgresapp.com/)
2. Drag to Applications folder
3. Open Postgres.app
4. Click "Initialize" to create a new server
5. Add to PATH (optional):
   ```bash
   echo 'export PATH="/Applications/Postgres.app/Contents/Versions/latest/bin:$PATH"' >> ~/.zshrc
   source ~/.zshrc
   ```

### Linux (Ubuntu/Debian)

```bash
# Update package list
sudo apt update

# Install PostgreSQL
sudo apt install postgresql postgresql-contrib

# Start PostgreSQL service
sudo systemctl start postgresql
sudo systemctl enable postgresql

# Verify installation
psql --version
```

### Linux (CentOS/RHEL)

```bash
# Install PostgreSQL
sudo yum install postgresql-server postgresql-contrib

# Initialize database
sudo postgresql-setup initdb

# Start and enable service
sudo systemctl start postgresql
sudo systemctl enable postgresql
```

### Windows

1. Download installer from [postgresql.org/download/windows/](https://www.postgresql.org/download/windows/)
2. Run the installer
3. Follow the setup wizard
4. Remember the password you set for the `postgres` user
5. Add PostgreSQL bin directory to PATH (usually `C:\Program Files\PostgreSQL\14\bin`)

## 🔧 Initial Configuration

### 1. Access PostgreSQL

```bash
# macOS/Linux - Access PostgreSQL as superuser
psql postgres

# Or if you created a user with your system username
psql
```

On Windows, use **pgAdmin** or **SQL Shell (psql)** from the Start menu.

### 2. Create Database and User

```sql
-- Create a database for Local Transparency
CREATE DATABASE local_transparency;

-- Create a user with password
CREATE USER transparency_user WITH PASSWORD 'your_secure_password';

-- Grant privileges
GRANT ALL PRIVILEGES ON DATABASE local_transparency TO transparency_user;

-- Exit psql
\q
```

### 3. Verify Connection

```bash
# Test connection with new user
psql -U transparency_user -d local_transparency -h localhost

# If successful, you'll see:
# local_transparency=>
```

## 📊 Database Schema

### For Stress Test Results

Create a table to store scraping results:

```sql
-- Connect to database
\c local_transparency

-- Create creatives table
CREATE TABLE creatives (
    id SERIAL PRIMARY KEY,
    creative_id TEXT UNIQUE NOT NULL,
    advertiser_id TEXT,
    url TEXT,
    status TEXT DEFAULT 'pending',
    video_count INTEGER,
    video_ids JSONB,  -- Store as JSON array
    appstore_id TEXT,
    scraped_at TIMESTAMP,
    error_message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create index for faster queries
CREATE INDEX idx_creative_status ON creatives(status);
CREATE INDEX idx_creative_scraped_at ON creatives(scraped_at);

-- Create function to auto-update updated_at
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Create trigger
CREATE TRIGGER update_creatives_updated_at 
    BEFORE UPDATE ON creatives 
    FOR EACH ROW 
    EXECUTE FUNCTION update_updated_at_column();
```

### Sample Data Schema

```sql
-- Table for tracking scraping sessions
CREATE TABLE scraping_sessions (
    id SERIAL PRIMARY KEY,
    session_name TEXT,
    start_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    end_time TIMESTAMP,
    total_urls INTEGER,
    success_count INTEGER DEFAULT 0,
    failed_count INTEGER DEFAULT 0,
    status TEXT DEFAULT 'running'
);

-- Table for detailed logs
CREATE TABLE scraping_logs (
    id SERIAL PRIMARY KEY,
    session_id INTEGER REFERENCES scraping_sessions(id),
    creative_id TEXT,
    url TEXT,
    status TEXT,
    video_count INTEGER,
    video_ids JSONB,
    appstore_id TEXT,
    duration_ms INTEGER,
    error_message TEXT,
    scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes
CREATE INDEX idx_logs_session_id ON scraping_logs(session_id);
CREATE INDEX idx_logs_status ON scraping_logs(status);
```

## 🐍 Python Connection

### Install PostgreSQL Adapter

```bash
# Install psycopg2-binary (already in requirements.txt)
pip3 install psycopg2-binary
```

### Connection Example

```python
import psycopg2
from psycopg2.extras import RealDictCursor

# Database configuration
DB_CONFIG = {
    'host': 'localhost',
    'database': 'local_transparency',
    'user': 'transparency_user',
    'password': 'your_secure_password',
    'port': 5432
}

# Connect to database
def get_db_connection():
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        return conn
    except Exception as e:
        print(f"Error connecting to database: {e}")
        return None

# Example usage
conn = get_db_connection()
if conn:
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute("SELECT version();")
    version = cursor.fetchone()
    print(f"PostgreSQL version: {version['version']}")
    cursor.close()
    conn.close()
```

### Environment Variables (Recommended)

Create a `.env` file in your project directory:

```bash
# .env file
DB_HOST=localhost
DB_PORT=5432
DB_NAME=local_transparency
DB_USER=transparency_user
DB_PASSWORD=your_secure_password
```

Install python-dotenv:

```bash
pip3 install python-dotenv
```

Load in Python:

```python
import os
from dotenv import load_dotenv
import psycopg2

# Load environment variables
load_dotenv()

# Database configuration from environment
DB_CONFIG = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'database': os.getenv('DB_NAME', 'local_transparency'),
    'user': os.getenv('DB_USER'),
    'password': os.getenv('DB_PASSWORD'),
    'port': int(os.getenv('DB_PORT', 5432))
}
```

## 🔍 Verification

### Check PostgreSQL Status

```bash
# macOS (Homebrew)
brew services list | grep postgresql

# Linux
sudo systemctl status postgresql

# Check if PostgreSQL is listening
pg_isready
```

### Test Python Connection

```bash
python3 -c "import psycopg2; print('✅ psycopg2 installed successfully')"
```

### List Databases

```bash
# List all databases
psql -l

# Connect to specific database
psql -U transparency_user -d local_transparency
```

## 🛠️ Common PostgreSQL Commands

```sql
-- List all databases
\l

-- Connect to database
\c local_transparency

-- List all tables
\dt

-- Describe table structure
\d creatives

-- Show table data
SELECT * FROM creatives LIMIT 10;

-- Count records by status
SELECT status, COUNT(*) FROM creatives GROUP BY status;

-- Exit psql
\q
```

## 🔧 Configuration Files

### PostgreSQL Configuration

Main config file locations:

- **macOS (Homebrew)**: `/usr/local/var/postgresql@<version>/postgresql.conf` or `/opt/homebrew/var/postgresql@<version>/postgresql.conf` (Apple Silicon)
- **Linux**: `/etc/postgresql/<version>/main/postgresql.conf`
- **Windows**: `C:\Program Files\PostgreSQL\<version>\data\postgresql.conf`

To find exact location on macOS:
```bash
brew info postgresql
```

### Allow Remote Connections (Optional)

Edit `postgresql.conf`:

```conf
listen_addresses = '*'  # Listen on all interfaces
```

Edit `pg_hba.conf`:

```conf
# Allow connections from any IP (use with caution!)
host    all             all             0.0.0.0/0               md5
```

Restart PostgreSQL after changes:

```bash
# macOS (Homebrew)
brew services restart postgresql@18

# Linux
sudo systemctl restart postgresql
```

## 📊 Database Maintenance

### Backup Database

```bash
# Backup to file
pg_dump -U transparency_user local_transparency > backup_$(date +%Y%m%d).sql

# Backup with compression
pg_dump -U transparency_user local_transparency | gzip > backup_$(date +%Y%m%d).sql.gz
```

### Restore Database

```bash
# Restore from backup
psql -U transparency_user local_transparency < backup_20251025.sql

# Restore from compressed backup
gunzip -c backup_20251025.sql.gz | psql -U transparency_user local_transparency
```

### Optimize Database

```sql
-- Vacuum and analyze (run periodically)
VACUUM ANALYZE creatives;

-- Reindex table
REINDEX TABLE creatives;
```

## 🆘 Troubleshooting

### Problem: "psql: command not found"

**Solution**: Add PostgreSQL to PATH

```bash
# macOS (Homebrew) - Intel
export PATH="/usr/local/opt/postgresql@18/bin:$PATH"

# macOS (Homebrew) - Apple Silicon
export PATH="/opt/homebrew/opt/postgresql@18/bin:$PATH"

# Or add to ~/.zshrc permanently
echo 'export PATH="/opt/homebrew/opt/postgresql@18/bin:$PATH"' >> ~/.zshrc  # Apple Silicon
echo 'export PATH="/usr/local/opt/postgresql@18/bin:$PATH"' >> ~/.zshrc     # Intel
```

### Problem: "FATAL: role does not exist"

**Solution**: Create the role (user)

```sql
CREATE USER transparency_user WITH PASSWORD 'your_password';
```

### Problem: "FATAL: database does not exist"

**Solution**: Create the database

```sql
CREATE DATABASE local_transparency;
```

### Problem: Connection refused

**Solution**: Start PostgreSQL service

```bash
# macOS (Homebrew)
brew services start postgresql@18

# Linux
sudo systemctl start postgresql
```

### Problem: "Peer authentication failed"

**Solution**: Edit `pg_hba.conf` to use md5 authentication:

```conf
# Change from:
local   all             all                                     peer

# To:
local   all             all                                     md5
```

Then restart PostgreSQL.

## 🔒 Security Best Practices

1. **Use Strong Passwords**: Never use default or weak passwords
2. **Limit Connections**: Only allow connections from trusted IPs
3. **Use Environment Variables**: Don't hardcode credentials in code
4. **Regular Backups**: Schedule automatic backups
5. **Update Regularly**: Keep PostgreSQL updated to latest version
6. **Restrict Permissions**: Grant only necessary privileges to users

## 📈 Performance Tuning (Optional)

For high-volume scraping, optimize PostgreSQL:

```sql
-- Increase shared buffers (in postgresql.conf)
shared_buffers = 256MB

-- Increase work memory
work_mem = 16MB

-- Increase maintenance work memory
maintenance_work_mem = 128MB

-- Enable parallel queries
max_parallel_workers_per_gather = 4
```

## 🎯 Next Steps

1. ✅ Install PostgreSQL
2. ✅ Create database and user
3. ✅ Install psycopg2-binary (`pip3 install -r requirements.txt`)
4. ✅ Create tables using the schema above
5. ✅ Test Python connection
6. ✅ Update your scraper scripts to use PostgreSQL

## 📚 Resources

- [PostgreSQL Official Documentation](https://www.postgresql.org/docs/)
- [psycopg2 Documentation](https://www.psycopg.org/docs/)
- [PostgreSQL Tutorial](https://www.postgresqltutorial.com/)

---

**Database**: PostgreSQL 12+  
**Python Adapter**: psycopg2-binary 2.9+  
**Last Updated**: October 2025

