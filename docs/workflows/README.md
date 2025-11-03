# Workflow Documentation

Complete guides for owners workflows and data processing pipelines.

## Available Workflows

1. **[DAILY_ADVERTISERS_COMPLETE_FLOW.md](DAILY_ADVERTISERS_COMPLETE_FLOW.md)**
   - Complete guide for BigQuery → GCS → Download → Import workflow
   - Daily advertisers data pipeline
   - Step-by-step instructions with actual project values

2. **[EFFICIENT_CSV_UPLOAD_PLAN.md](EFFICIENT_CSV_UPLOAD_PLAN.md)**
   - Plan for efficiently uploading 3.5M rows from CSV to PostgreSQL
   - Performance strategies (temp table + COPY method)
   - Minimizing lock contention

## Related Documentation

- Database setup: `../DATABASE_SETUP.md`
- Import guide: `../IMPORT_GUIDE.md`
- Database config: `../DATABASE_CONFIG.md`


