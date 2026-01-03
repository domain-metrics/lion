#!/usr/bin/env python3
"""
Flask Server - Queue Management Only
Receives requests and adds them to a shared queue (Redis or file-based)
"""

import json
import time
import subprocess
import os
from datetime import datetime
from flask import Flask, jsonify, request
from pathlib import Path

app = Flask(__name__)

# Configuration
QUEUE_DIR = "queue"
RESULTS_DIR = "results"
WORKER_DIR = "worker"
QUEUE_FILE = f"{QUEUE_DIR}/task_queue.json"
RESULTS_FILE = f"{RESULTS_DIR}/results.json"
HEARTBEAT_TIMEOUT = 30  # seconds (consider worker dead if heartbeat older than this)

# Create directories if they don't exist
Path(QUEUE_DIR).mkdir(exist_ok=True)
Path(RESULTS_DIR).mkdir(exist_ok=True)
Path(WORKER_DIR).mkdir(exist_ok=True)

def load_json_file(filename, default=None):
    """Load JSON file safely"""
    try:
        if Path(filename).exists():
            with open(filename, 'r') as f:
                return json.load(f)
    except:
        pass
    return default if default is not None else []

def save_json_file(filename, data):
    """Save JSON file safely"""
    with open(filename, 'w') as f:
        json.dump(data, f, indent=2)

def parse_proxy(proxy_string):
    """Parse proxy string in format: ip:port:user:pass"""
    if not proxy_string:
        return None
    
    parts = proxy_string.split(':')
    if len(parts) >= 4:
        return {
            'server': f"http://{parts[0]}:{parts[1]}",
            'username': parts[2],
            'password': parts[3]
        }
    return None

def count_active_workers():
    """Count active workers based on heartbeat files"""
    active_count = 0
    current_time = time.time()
    
    # Find all worker heartbeat files in worker directory
    for heartbeat_file in Path(WORKER_DIR).glob('worker_*_heartbeat.json'):
        try:
            heartbeat_data = load_json_file(str(heartbeat_file), {})
            timestamp = heartbeat_data.get('timestamp', 0)
            pid = heartbeat_data.get('pid')
            
            # Check if heartbeat is recent
            if current_time - timestamp < HEARTBEAT_TIMEOUT and pid:
                # Verify the process actually exists
                try:
                    os.kill(pid, 0)  # Signal 0 doesn't kill, just checks if process exists
                    active_count += 1
                except (ProcessLookupError, PermissionError):
                    # Process doesn't exist, remove stale heartbeat file
                    try:
                        Path(heartbeat_file).unlink()
                    except:
                        pass
        except:
            pass
    
    return active_count

# ============================================================================
# Flask Routes
# ============================================================================

@app.route('/load', methods=['POST'])
def load_domain():
    """Load a single domain - adds to queue"""
    data = request.json or {}
    domain = data.get('domain')
    
    if not domain:
        return jsonify({'error': 'domain is required'}), 400
    
    # Load current queue
    queue = load_json_file(QUEUE_FILE, [])
    
    # Add task (no proxy - workers have their own proxies)
    task = {
        'domain': domain,
        'added_at': datetime.now().isoformat(),
        'status': 'queued'
    }
    queue.append(task)
    
    # Save queue
    save_json_file(QUEUE_FILE, queue)
    
    return jsonify({
        'message': 'Task added to queue',
        'domain': domain,
        'queue_position': len(queue)
    })


@app.route('/batch', methods=['POST'])
def batch_load():
    """Load multiple domains - adds to queue"""
    data = request.json or {}
    domains = data.get('domains', [])
    
    if not domains:
        return jsonify({'error': 'domains array is required'}), 400
    
    # Load current queue
    queue = load_json_file(QUEUE_FILE, [])
    
    # Add all domains (no proxy - workers have their own proxies)
    added = []
    for domain in domains:
        task = {
            'domain': domain,
            'added_at': datetime.now().isoformat(),
            'status': 'queued'
        }
        queue.append(task)
        added.append({'domain': domain, 'queue_position': len(queue)})
    
    # Save queue
    save_json_file(QUEUE_FILE, queue)
    
    return jsonify({
        'message': f'Added {len(domains)} domains to queue',
        'domains': added,
        'queue_length': len(queue)
    })


@app.route('/queue', methods=['GET'])
def get_queue_status():
    """Get current queue status"""
    queue = load_json_file(QUEUE_FILE, [])
    results = load_json_file(RESULTS_FILE, {'completed': [], 'failed': []})
    
    queued_domains = [task['domain'] for task in queue if task.get('status') == 'queued']
    processing_domains = [task['domain'] for task in queue if task.get('status') == 'processing']
    
    return jsonify({
        'queue_length': len([t for t in queue if t.get('status') == 'queued']),
        'processing_count': len([t for t in queue if t.get('status') == 'processing']),
        'queued_domains': queued_domains,
        'processing_domains': processing_domains,
        'completed_count': len(results.get('completed', [])),
        'failed_count': len(results.get('failed', []))
    })


@app.route('/queue/details', methods=['GET'])
def get_queue_details():
    """Get detailed queue information"""
    queue = load_json_file(QUEUE_FILE, [])
    
    return jsonify({
        'queue': queue,
        'queue_length': len(queue)
    })


@app.route('/results', methods=['GET'])
def get_results():
    """Get all results"""
    results = load_json_file(RESULTS_FILE, {'completed': [], 'failed': []})
    
    return jsonify({
        'completed': results.get('completed', []),
        'failed': results.get('failed', []),
        'total': len(results.get('completed', [])) + len(results.get('failed', []))
    })


@app.route('/results/clear', methods=['POST'])
def clear_results():
    """Clear all results"""
    save_json_file(RESULTS_FILE, {'completed': [], 'failed': []})
    return jsonify({'message': 'Results cleared'})


@app.route('/queue/clear', methods=['POST'])
def clear_queue():
    """Clear the queue"""
    save_json_file(QUEUE_FILE, [])
    return jsonify({'message': 'Queue cleared'})


@app.route('/health', methods=['GET'])
def health():
    """Health check"""
    return jsonify({
        'status': 'healthy',
        'server': 'running'
    })


@app.route('/workers', methods=['GET'])
def get_workers():
    """Get active worker count"""
    active_workers = count_active_workers()
    
    return jsonify({
        'active_workers': active_workers
    })


@app.route('/workers/details', methods=['GET'])
def get_workers_details():
    """Get detailed worker information including proxies"""
    workers = []
    current_time = time.time()
    
    for heartbeat_file in Path(WORKER_DIR).glob('worker_*_heartbeat.json'):
        try:
            heartbeat_data = load_json_file(str(heartbeat_file), {})
            timestamp = heartbeat_data.get('timestamp', 0)
            pid = heartbeat_data.get('pid')
            proxy = heartbeat_data.get('proxy')
            
            # Check if heartbeat is recent and process exists
            if current_time - timestamp < HEARTBEAT_TIMEOUT and pid:
                try:
                    os.kill(pid, 0)  # Check if process exists
                    workers.append({
                        'pid': pid,
                        'proxy': proxy if proxy else 'no proxy',
                        'last_heartbeat': heartbeat_data.get('last_updated'),
                        'age_seconds': int(current_time - timestamp)
                    })
                except (ProcessLookupError, PermissionError):
                    pass
        except:
            pass
    
    return jsonify({
        'active_workers': len(workers),
        'workers': workers
    })


@app.route('/scale', methods=['GET', 'POST'])
def scale_workers():
    """Start or kill workers based on scale parameter
    
    GET /scale?scale=3  - Scale to 3 workers (no proxy)
    POST /scale with JSON body:
    {
        "scale": 3,
        "proxies": ["ip:port:user:pass", "ip:port:user:pass", ...]
    }
    """
    try:
        # Handle GET or POST
        if request.method == 'POST':
            data = request.json or {}
            scale = int(data.get('scale', -1))
            proxies = data.get('proxies', [])
        else:
            scale = int(request.args.get('scale', -1))
            proxies = []
        
        if scale < 0:
            return jsonify({'error': 'scale must be >= 0'}), 400
        
        # Get current active workers
        current_workers = count_active_workers()
        
        # Get worker PIDs from heartbeat files
        worker_pids = []
        current_time = time.time()
        for heartbeat_file in Path(WORKER_DIR).glob('worker_*_heartbeat.json'):
            try:
                heartbeat_data = load_json_file(str(heartbeat_file), {})
                timestamp = heartbeat_data.get('timestamp', 0)
                pid = heartbeat_data.get('pid')
                
                if current_time - timestamp < HEARTBEAT_TIMEOUT and pid:
                    worker_pids.append(pid)
            except:
                pass
        
        # Calculate difference
        diff = scale - current_workers
        
        # SCALE UP - Start more workers
        if diff > 0:
            project_dir = os.path.dirname(os.path.abspath(__file__))
            venv_python = os.path.join(project_dir, '.venv', 'bin', 'python3')
            worker_script = os.path.join(project_dir, 'worker.py')
            
            started_pids = []
            started_proxies = []
            
            for i in range(diff):
                # Get proxy for this worker (if available)
                proxy = proxies[i] if i < len(proxies) else None
                
                # Build command
                cmd = [venv_python, worker_script]
                if proxy:
                    cmd.extend(['--proxy', proxy])
                
                process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    start_new_session=True,
                    cwd=project_dir
                )
                started_pids.append(process.pid)
                started_proxies.append(proxy if proxy else "no proxy")
            
            time.sleep(2)
            new_worker_count = count_active_workers()
            
            return jsonify({
                'message': f'Started {diff} workers',
                'requested_scale': scale,
                'previous_workers': current_workers,
                'active_workers': new_worker_count,
                'workers_started': diff,
                'started_pids': started_pids,
                'proxies_assigned': started_proxies
            })
        
        # SCALE DOWN - Kill workers
        elif diff < 0:
            workers_to_kill = abs(diff)
            killed_pids = []
            
            for i in range(min(workers_to_kill, len(worker_pids))):
                pid = worker_pids[i]
                try:
                    os.kill(pid, 15)  # SIGTERM for graceful shutdown
                    killed_pids.append(pid)
                except:
                    pass
            
            time.sleep(2)
            new_worker_count = count_active_workers()
            
            return jsonify({
                'message': f'Killed {len(killed_pids)} workers',
                'requested_scale': scale,
                'previous_workers': current_workers,
                'active_workers': new_worker_count,
                'workers_killed': len(killed_pids),
                'killed_pids': killed_pids
            })
        
        # NO CHANGE
        else:
            return jsonify({
                'message': f'Already at scale {scale}',
                'requested_scale': scale,
                'active_workers': current_workers,
                'workers_changed': 0
            })
        
    except ValueError:
        return jsonify({'error': 'scale must be a valid integer'}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ============================================================================
# Main
# ============================================================================

if __name__ == '__main__':
    print("=" * 80)
    print("🚀 Starting Flask Server (Queue Manager)")
    print("=" * 80)
    print("Server: Receives HTTP requests")
    print("Queue: Stored in task_queue.json")
    print("Results: Stored in results.json")
    print("Worker: Run worker.py separately")
    print("=" * 80)
    
    # Initialize files if they don't exist
    if not Path(QUEUE_FILE).exists():
        save_json_file(QUEUE_FILE, [])
    if not Path(RESULTS_FILE).exists():
        save_json_file(RESULTS_FILE, {'completed': [], 'failed': []})
    
    print("✅ Server ready!")
    print("=" * 80)
    
    app.run(host='0.0.0.0', port=5001, debug=False, threaded=True)

