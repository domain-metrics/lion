# API Test Script

## Overview

This script tests the API with both proxy and non-proxy batch processing.

## What It Tests

1. **Test 1: WITHOUT PROXY**
   - Submits 20 domains without proxy
   - Monitors progress in real-time
   - Shows results

2. **Test 2: WITH PROXY**
   - Submits 20 domains with proxy from Webshare file
   - Monitors progress in real-time
   - Shows results

## Test Domains (20 domains)

- example.com
- stackoverflow.com
- github.com
- reddit.com
- wikipedia.org
- amazon.com
- twitter.com
- linkedin.com
- youtube.com
- facebook.com
- netflix.com
- spotify.com
- apple.com
- microsoft.com
- google.com
- instagram.com
- tiktok.com
- pinterest.com
- tumblr.com
- medium.com

## Prerequisites

1. Flask server must be running:
   ```bash
   source .venv/bin/activate
   python3 flask_server.py
   ```

2. Proxy file must exist (optional, for Test 2):
   ```
   ../Webshare 100 proxies.txt
   ```

## Usage

```bash
cd test
python3 test_api.py
```

## What It Does

1. **Clears** queue and results
2. **Scales** to 3 workers
3. **Submits** 20 domains (Test 1: no proxy)
4. **Monitors** progress in real-time
5. **Shows** results with DR, backlinks, linking websites
6. **Submits** 20 domains (Test 2: with proxy)
7. **Monitors** progress in real-time
8. **Shows** results
9. **Displays** summary

## Expected Output

```
================================================================================
🧪 API TEST SCRIPT
================================================================================

🧹 Clearing queue and results...
   ✅ Cleared

⚙️  Scaling to 3 workers...
   ✅ Started 3 workers
   📊 Active workers: 3

================================================================================
TEST 1: WITHOUT PROXY (20 domains)
================================================================================

📤 Submitting 20 domains (No Proxy)...
   🌐 No proxy (direct connection)
   ✅ Added 20 domains to queue
   📊 Queue length: 20

⏳ Monitoring progress...
   ⏱️  2s | Queue: 17 | Processing: 3 | Completed: 0 | Failed: 0
   ⏱️  15s | Queue: 14 | Processing: 3 | Completed: 3 | Failed: 0
   ...
   ✅ Processing complete!

📊 Fetching results...
   ✅ Completed: 18
   ❌ Failed: 2
   📈 Total: 20

   📝 Sample completed results:
      1. example.com              | DR:   45 | Backlinks:   125000 | Linking:  15000 | Time: 12.3s
      2. stackoverflow.com        | DR:   91 | Backlinks: 15000000 | Linking: 125000 | Time: 13.5s
      ...

✅ TEST 1 COMPLETE: 18 completed, 2 failed

================================================================================
TEST 2: WITH PROXY (20 domains)
================================================================================

📤 Submitting 20 domains (With Proxy)...
   🔒 Using proxy: 123.45.67.89:8080:user:pass...
   ✅ Added 20 domains to queue
   📊 Queue length: 20

⏳ Monitoring progress...
   ...
   ✅ Processing complete!

📊 Fetching results...
   ✅ Completed: 19
   ❌ Failed: 1
   📈 Total: 20

✅ TEST 2 COMPLETE: 19 completed, 1 failed

================================================================================
📊 TEST SUMMARY
================================================================================

Test 1 (No Proxy):  18 completed, 2 failed
Test 2 (With Proxy): 19 completed, 1 failed

================================================================================
✅ ALL TESTS COMPLETE!
================================================================================
```

## Features

- ✅ Real-time progress monitoring
- ✅ Automatic queue clearing
- ✅ Automatic worker scaling
- ✅ Proxy and non-proxy testing
- ✅ Detailed result display
- ✅ Error handling
- ✅ Summary statistics

## Notes

- Test takes ~10-15 minutes to complete (40 domains total)
- Uses 3 workers for concurrent processing
- Automatically waits between tests
- Press Ctrl+C to interrupt at any time

