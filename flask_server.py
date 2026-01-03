#!/usr/bin/env python3
"""
Flask Server - Queue Management Only
Receives requests and adds them to a shared queue (Redis or file-based)
"""

import json
import time
from datetime import datetime
from flask import Flask, jsonify, request
from pathlib import Path

app = Flask(__name__)

# Configuration
QUEUE_FILE = "task_queue.json"
RESULTS_FILE = "results.json"
STATUS_FILE = "worker_status.json"

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
    
    # Parse proxy if provided
    proxy = None
    if data.get('proxy'):
        proxy = parse_proxy(data['proxy'])
    
    # Load current queue
    queue = load_json_file(QUEUE_FILE, [])
    
    # Add task
    task = {
        'domain': domain,
        'proxy': proxy,
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
    
    # Parse proxy if provided (same proxy for all domains)
    proxy = None
    if data.get('proxy'):
        proxy = parse_proxy(data['proxy'])
    
    # Load current queue
    queue = load_json_file(QUEUE_FILE, [])
    
    # Add all domains
    added = []
    for domain in domains:
        task = {
            'domain': domain,
            'proxy': proxy,
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
    worker_status = load_json_file(STATUS_FILE, {})
    
    queued_domains = [task['domain'] for task in queue if task.get('status') == 'queued']
    processing_domains = [task['domain'] for task in queue if task.get('status') == 'processing']
    
    return jsonify({
        'queue_length': len([t for t in queue if t.get('status') == 'queued']),
        'processing_count': len([t for t in queue if t.get('status') == 'processing']),
        'queued_domains': queued_domains,
        'processing_domains': processing_domains,
        'completed_count': len(results.get('completed', [])),
        'failed_count': len(results.get('failed', [])),
        'worker_status': worker_status
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
    worker_status = load_json_file(STATUS_FILE, {})
    
    return jsonify({
        'status': 'healthy',
        'server': 'running',
        'worker_status': worker_status.get('status', 'unknown'),
        'worker_last_heartbeat': worker_status.get('last_heartbeat', 'unknown')
    })


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
    if not Path(STATUS_FILE).exists():
        save_json_file(STATUS_FILE, {'status': 'stopped', 'last_heartbeat': None})
    
    print("✅ Server ready!")
    print("=" * 80)
    
    app.run(host='0.0.0.0', port=5001, debug=False, threaded=True)

