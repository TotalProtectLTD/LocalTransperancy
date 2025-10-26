# Installation Checklist - Local Transparency

Quick verification checklist for Local Transparency setup.

## ✅ System Requirements

- [ ] **Python 3.7+** installed (`python3 --version`)
- [ ] **PostgreSQL 18** installed (`brew install postgresql@18`)
- [ ] **pip3** available (`pip3 --version`)
- [ ] **Internet connection** active

## ✅ Installation Steps

### 1. PostgreSQL Database
- [ ] Install PostgreSQL 18
  ```bash
  brew install postgresql@18
  brew services start postgresql@18
  ```

- [ ] Add to PATH (Apple Silicon with Homebrew)
  ```bash
  echo 'export PATH="/opt/homebrew/opt/postgresql@18/bin:$PATH"' >> ~/.zshrc
  source ~/.zshrc
  ```

- [ ] Create database
  ```bash
  psql postgres
  # CREATE DATABASE local_transparency;
  # CREATE USER transparency_user WITH PASSWORD 'your_password';
  # GRANT ALL PRIVILEGES ON DATABASE local_transparency TO transparency_user;
  ```

### 2. Python Dependencies
- [ ] Install packages
  ```bash
  pip3 install -r requirements.txt
  ```

- [ ] Verify PostgreSQL adapter
  ```bash
  python3 -c "import psycopg2; print('✅ PostgreSQL adapter OK')"
  ```

### 3. Browser
- [ ] Install Chromium
  ```bash
  playwright install chromium
  ```

### 4. Test Installation
- [ ] Test main scraper
  ```bash
  python3 google_ads_transparency_scraper.py --help
  ```

- [ ] Test database connection
  ```bash
  psql -U transparency_user -d local_transparency
  ```

## ✅ Optional Components

- [ ] **mitmproxy** (for traffic measurement)
  ```bash
  pip3 install mitmproxy
  ```

## 🚀 Quick Verification

Run this to check everything:

```bash
python3 --version && \
psql --version && \
python3 -c "import psycopg2, playwright, httpx; print('✅ All packages OK')" && \
python3 google_ads_transparency_scraper.py --help > /dev/null && \
echo "✅ Ready to use!"
```

## 📖 Next Steps

1. ✅ Complete this checklist
2. ✅ Read `QUICKSTART.md` for usage examples
3. ✅ Try scraping a single URL
4. ✅ Read `README.md` for full documentation

---

**Last Updated**: October 2025

