# Database Backups

This directory stores PostgreSQL database backups.

## Usage

### Create a backup:
```bash
python3 backup_database.py
```

### Create a backup with custom name:
```bash
python3 backup_database.py backup_before_migration.sql
```

### List all backups:
```bash
python3 backup_database.py --list
```

### Restore a backup:
```bash
psql -U transparency_user -d local_transparency < db_backups/backup_YYYYMMDD_HHMMSS.sql
```

## Backup Files

Backup files are automatically ignored by git (see `.gitignore`).
Only the folder structure and this README are tracked.

## Best Practices

1. **Create a backup before any migration:**
   ```bash
   python3 backup_database.py backup_before_advertisers_table.sql
   ```

2. **Regular backups:**
   - Before schema changes
   - Before bulk data operations
   - Before major updates

3. **Verify backup:**
   ```bash
   # Check file exists and has size > 0
   ls -lh db_backups/backup_*.sql
   ```

4. **Test restore on staging** before using in production
