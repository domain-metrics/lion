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
python3 server.py




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

# Test 9: Check server health
curl http://127.0.0.1:8000/health