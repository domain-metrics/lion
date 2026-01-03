1. Create droplet from Ubuntu GNOME
2. Wait for 5 mins - than - Launch Droplet Console 
3. Find User and VNC Password
4. connect via vnc viewer
5. Login with user - and given password.
6. Search "display" make resolution 1792x1344
7. RUN Now : 

apt install python3-pip
curl -fsSL https://tailscale.com/install.sh | sh && sudo tailscale up --authkey=tskey-auth-kiWHkAm3W321CNTRL-cPFdmFaQXLNh1qyKztRzKN3N6rq5L7R5

8. Type Manually - 

git clone https://github.com/domain-metrics/lion.git 

9. Get data from readme - cat readme.txt

python3 -m camoufox fetch
python3 run.py




# ========================================
# TEST COMMANDS
# ========================================

# Test 1: Verify proxy is working (should return proxy's IP: 23.27.196.104)
curl -x http://tjijutki:4vg93ifc50gnx@23.27.196.104:6473 "https://api.ipify.org?format=json"

# Test 2: Submit scrape job WITH proxy
curl -X POST http://127.0.0.1:8000/scrape \
  -H "Content-Type: application/json" \
  -d '{"domain":"techcrunch.com","proxy_ip":"23.27.196.104","proxy_port":"6473","proxy_user":"tjijutki","proxy_pass":"4vg93ifc50gnx"}'

# Test 3: Submit scrape job WITHOUT proxy  
curl -X POST http://127.0.0.1:8000/scrape \
  -H "Content-Type: application/json" \
  -d '{"domain":"techcrunch.com"}'

# Test 4: Batch scrape with multiple domains (simple - no proxies)
curl -X POST http://127.0.0.1:8000/batch \
  -H "Content-Type: application/json" \
  -d '{"domains":["techcrunch.com","example.com","github.com"]}'

# Test 5: Batch scrape with different proxy for each domain
curl -X POST http://127.0.0.1:8000/batch \
  -H "Content-Type: application/json" \
  -d '{
    "domains": [
      {
        "domain": "techcrunch.com",
        "proxy_ip": "23.27.196.104",
        "proxy_port": "6473",
        "proxy_user": "tjijutki",
        "proxy_pass": "4vg93ifc50gnx"
      },
      {
        "domain": "example.com",
        "proxy_ip": "23.27.196.104",
        "proxy_port": "6473",
        "proxy_user": "tjijutki",
        "proxy_pass": "4vg93ifc50gnx"
      },
      {
        "domain": "github.com"
      }
    ]
  }'

# Test 6: Check job result (replace TASK_ID with the task_id from response above)
curl http://127.0.0.1:8000/result/TASK_ID

# Test 7: List all jobs
curl http://127.0.0.1:8000/jobs

# Test 8: List only completed jobs
curl "http://127.0.0.1:8000/jobs?status=completed"

# Test 9: Check current queue status
curl http://127.0.0.1:8000/queue

# Test 10: Check server health
curl http://127.0.0.1:8000/health

# ========================================
# NOTES
# ========================================
# - All jobs are processed through a queue with concurrent processing
# - Up to 3 tasks can process simultaneously (3 workers)
# - When you submit a batch, domains are added to a queue
# - Tasks start immediately up to the 3 concurrent limit
# - When a page loads (network idle), next domain from queue starts
# - This balances throughput with browser stability
# - Job status flow: queued -> processing -> completed/failed

# ========================================
# FILE STRUCTURE
# ========================================
# run.py             - Main Flask application & queue management
# camoufox_helper.py - Browser initialization & context pooling
# ahrefs_helper.py   - Ahrefs scraping logic (CAPTCHA, metrics)

# ========================================
# ARCHITECTURE (Test 4 Approach for ALL - 100% Success)
# ========================================
# WITHOUT proxy:
#   - Uses ONE shared context for all non-proxy requests
#   - Creates pages only (NO new contexts per request)
#   - 100% success rate (NO timeouts, NO page loading issues)
#
# WITH proxy:
#   - Uses ONE shared context per unique proxy (context pooling)
#   - Creates pages only (NO new contexts per request)
#   - Each proxy gets its own shared context (created once, reused)
#   - Example: 100 proxies = 100 shared contexts (not 1000 contexts for 1000 requests)
#
# - Semaphores to prevent Camoufox deadlock (issue #279):
#   * context creation serialized
#   * page creation serialized
#   * page.goto() serialized
# - Concurrent processing: 3 workers (MAX_CONCURRENT_PROCESSING = 3)
# - Browser instance is shared and persistent across all requests
# 
# Why Test 4 Approach for Both?
# - Test 4 achieved 100% success (30/30 tasks)
# - NO first-byte timeout issues
# - NO page loading issues
# - Full proxy support with context pooling
# - Much faster (contexts are reused, not created per request)
# - Simpler and more reliable

# ========================================
# TESTING SCRIPTS
# ========================================
# Test direct scraping (NO Flask) - Pure Test 4 approach
python3 test_direct_scraping.py

# Features:
# - NO Flask (pure asyncio)
# - NO semaphore (Test 4 approach)
# - Uses asyncio.gather() for true concurrent execution
# - Shared contexts + pages only
# - Edit domains_100.txt to test with your own domains
# - Edit MAX_CONCURRENT_WORKERS (default: 3, set to 0 for ALL domains)