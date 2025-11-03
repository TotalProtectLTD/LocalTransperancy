# Tests

This directory contains all test scripts for the Local Transparency project.

## Test Files

### Cache Tests
- **test_cache_simple.py** - Simple cache functionality test
- **test_cache_fix.py** - Cache fix validation
- **test_cache_integration.py** - Cache integration test
- **test_cache_with_proxy.py** - Cache test with mitmproxy
- **test_memory_cache.py** - Memory cache specific tests

### Scraper Tests
- **test_optimized_scraper.py** - Optimized scraper tests
- **test_optimized_batch_fix.py** - Batch processing fix tests
- **test_simple_batch.py** - Simple batch processing test
- **test_full_integration.py** - Full integration tests
- **test_with_real_data.py** - Tests with real data
- **test_session_reuse.py** - Session reuse functionality tests

### Proxy & Network Tests
- **test_partial_proxy.py** - Partial proxy implementation tests
- **test_batch_with_mitmproxy.py** - Batch tests with mitmproxy

### Utility Tests
- **test_compare_methods.py** - Method comparison tests
- **test_context_replication.py** - Context replication tests
- **test_debug_save_all.py** - Debug file saving tests
- **test_logging_impact.py** - Logging impact analysis
- **test_database.py** - Database functionality tests

## Running Tests

Tests are independent scripts that can be run directly:

```bash
# From project root
python3 tests/test_cache_simple.py
python3 tests/test_full_integration.py
```

## Note

These test files are not imported by main application files. They are standalone test scripts for validation and debugging purposes.


