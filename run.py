#!/usr/bin/env python3
"""
Ahrefs Scraper Flask Application

Main entry point for the scraping server.
Uses queue system with 3 concurrent workers (Test 4 approach).
"""

from flask import Flask, request, jsonify
import asyncio
from threading import Thread
import uuid
from datetime import datetime
from dotenv import load_dotenv
import socket

# Import helpers
from camoufox_helper import initialize_browser, close_browser, get_context_pool_stats
from ahrefs_helper import scrape_ahrefs_domain

load_dotenv()

app = Flask(__name__)

# In-memory storage for jobs and results
jobs = {}
results = {}

# Global event loop for all async operations
global_loop = None
loop_thread = None

# Task queue for concurrent processing
task_queue = []
queue_lock = asyncio.Lock()

# Concurrent processing control (3 workers, Test 4 approach, NO semaphore)
MAX_CONCURRENT_PROCESSING = 2
current_processing_count = 0
processing_count_lock = asyncio.Lock()


# ============================================================================
# Queue Management Functions
# ============================================================================

async def process_next_task():
    """Process one task from the queue (up to MAX_CONCURRENT_PROCESSING at a time)"""
    global task_queue, current_processing_count
    
    # Get next task
    async with queue_lock:
        if len(task_queue) == 0:
            print("📭 Queue empty - no more tasks")
            return
        
        task = task_queue.pop(0)
        task_id = task['task_id']
        domain = task['domain']
        proxy = task.get('proxy')
    
    # Increment processing count
    async with processing_count_lock:
        current_processing_count += 1
        processing = current_processing_count
    
    # Process this task
    print(f"🔄 Processing from queue: {domain} (Processing: {processing}/{MAX_CONCURRENT_PROCESSING}, Queue: {len(task_queue)})")
    
    # Callback to trigger next task when page loads
    async def on_page_loaded():
        print(f"✨ Page loaded for {domain}, checking for next task...")
        await start_next_if_possible()
    
    try:
        jobs[task_id]['status'] = 'processing'
        jobs[task_id]['started_at'] = datetime.now().isoformat()
        
        # Scrape the domain
        result = await scrape_ahrefs_domain(domain, proxy, page_loaded_callback=on_page_loaded)
        
        jobs[task_id]['status'] = 'completed'
        jobs[task_id]['completed_at'] = datetime.now().isoformat()
        results[task_id] = result
        
        print(f"✅ Task {task_id} completed: {domain}")
        
    except Exception as e:
        jobs[task_id]['status'] = 'failed'
        jobs[task_id]['error'] = str(e)
        jobs[task_id]['completed_at'] = datetime.now().isoformat()
        print(f"❌ Task {task_id} failed: {e}")
    
    finally:
        # Decrement processing count
        async with processing_count_lock:
            current_processing_count -= 1
            processing = current_processing_count
        
        print(f"🏁 Task finished: {domain} (Processing now: {processing}/{MAX_CONCURRENT_PROCESSING})")
        
        # Try to start next task
        await start_next_if_possible()


async def start_next_if_possible():
    """Start next task from queue if under the concurrent limit"""
    global current_processing_count
    
    async with processing_count_lock:
        can_start = current_processing_count < MAX_CONCURRENT_PROCESSING
        processing = current_processing_count
    
    if can_start and len(task_queue) > 0:
        print(f"🚀 Starting next task (Processing: {processing}/{MAX_CONCURRENT_PROCESSING})")
        asyncio.create_task(process_next_task())
    elif processing >= MAX_CONCURRENT_PROCESSING:
        print(f"⏸️  At capacity ({MAX_CONCURRENT_PROCESSING}/{MAX_CONCURRENT_PROCESSING}), waiting for slot...")
    else:
        print(f"📭 No more tasks in queue")


async def add_task_to_queue(task_id, domain, proxy=None):
    """Add a task to the queue and start processing if capacity available"""
    global task_queue, current_processing_count
    
    # Add task to queue
    async with queue_lock:
        task_queue.append({
            'task_id': task_id,
            'domain': domain,
            'proxy': proxy
        })
        queue_size = len(task_queue)
    
    async with processing_count_lock:
        processing = current_processing_count
    
    print(f"📥 Added to queue: {domain} (Queue: {queue_size}, Processing: {processing}/{MAX_CONCURRENT_PROCESSING})")
    
    # Try to start this task if we have capacity
    await start_next_if_possible()


def run_async_task(task_id, domain, proxy=None):
    """Submit task to the queue via global event loop"""
    global global_loop
    
    if global_loop is None:
        print(f"❌ Global loop not initialized")
        return
    
    # Add task to queue (will be processed based on capacity)
    asyncio.run_coroutine_threadsafe(add_task_to_queue(task_id, domain, proxy), global_loop)


# ============================================================================
# Flask Routes
# ============================================================================

@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'tailscale_ip': get_tailscale_ip(),
        'total_jobs': len(jobs),
        'queued': len([j for j in jobs.values() if j['status'] == 'queued']),
        'processing': len([j for j in jobs.values() if j['status'] == 'processing']),
        'completed': len([j for j in jobs.values() if j['status'] == 'completed']),
        'failed': len([j for j in jobs.values() if j['status'] == 'failed']),
        'queue_size': len(task_queue),
        'max_concurrent': MAX_CONCURRENT_PROCESSING,
        'current_processing': current_processing_count,
        'context_pool': get_context_pool_stats()
    })


@app.route('/queue', methods=['GET'])
def queue_status():
    """Get current queue status"""
    queue_items = []
    for task in task_queue:
        queue_items.append({
            'task_id': task['task_id'],
            'domain': task['domain'],
            'has_proxy': task.get('proxy') is not None
        })
    
    return jsonify({
        'queue_size': len(task_queue),
        'processing_count': len([j for j in jobs.values() if j['status'] == 'processing']),
        'queue': queue_items
    })


@app.route('/scrape', methods=['POST'])
def scrape():
    """Submit a single scraping job"""
    data = request.get_json()
    domain = data.get('domain')
    
    if not domain:
        return jsonify({'error': 'Domain is required'}), 400
    
    # Create job
    task_id = str(uuid.uuid4())
    
    # Parse proxy if provided
    proxy = None
    if data.get('proxy_ip'):
        proxy = {
            'server': f"http://{data['proxy_ip']}:{data['proxy_port']}",
            'username': data.get('proxy_user'),
            'password': data.get('proxy_pass')
        }
    
    jobs[task_id] = {
        'task_id': task_id,
        'domain': domain,
        'status': 'queued',
        'created_at': datetime.now().isoformat(),
        'proxy': proxy.get('server') if proxy else None
    }
    
    proxy_info = f" [proxy: {proxy.get('server')}]" if proxy else ""
    print(f"📥 New job {task_id}: {domain}{proxy_info}")
    
    # Add to queue (will be processed based on capacity)
    run_async_task(task_id, domain, proxy)
    
    return jsonify({
        'task_id': task_id,
        'status': 'queued',
        'message': 'Job queued successfully'
    }), 202


@app.route('/batch', methods=['POST'])
def batch_scrape():
    """Submit multiple scraping jobs"""
    data = request.get_json()
    domains_data = data.get('domains', [])
    
    if not domains_data:
        return jsonify({'error': 'Domains list is required'}), 400
    
    task_ids = []
    
    for item in domains_data:
        # Handle both string domains and dict with proxy info
        if isinstance(item, str):
            domain = item
            proxy = None
        else:
            domain = item.get('domain')
            proxy = None
            if item.get('proxy_ip'):
                proxy = {
                    'server': f"http://{item['proxy_ip']}:{item['proxy_port']}",
                    'username': item.get('proxy_user'),
                    'password': item.get('proxy_pass')
                }
        
        if not domain:
            continue
        
        task_id = str(uuid.uuid4())
        
        jobs[task_id] = {
            'task_id': task_id,
            'domain': domain,
            'status': 'queued',
            'created_at': datetime.now().isoformat(),
            'proxy': proxy.get('server') if proxy else None
        }
        
        task_ids.append(task_id)
        
        # Add to queue
        run_async_task(task_id, domain, proxy)
    
    print(f"📥 Batch job: {len(task_ids)} domains queued")
    
    return jsonify({
        'task_ids': task_ids,
        'message': f'{len(task_ids)} jobs queued',
        'note': 'Jobs will be processed sequentially through the queue'
    }), 202


@app.route('/result/<task_id>', methods=['GET'])
def get_result(task_id):
    """Get result for a specific job"""
    if task_id not in jobs:
        return jsonify({'error': 'Job not found'}), 404
    
    job = jobs[task_id]
    response = {
        'task_id': task_id,
        'domain': job['domain'],
        'status': job['status'],
        'created_at': job['created_at'],
        'proxy': job.get('proxy')
    }
    
    if job['status'] == 'completed':
        response['result'] = results.get(task_id)
        response['completed_at'] = job.get('completed_at')
    elif job['status'] == 'failed':
        response['error'] = job.get('error')
        response['completed_at'] = job.get('completed_at')
    elif job['status'] == 'processing':
        response['started_at'] = job.get('started_at')
    
    return jsonify(response)


@app.route('/jobs', methods=['GET'])
def list_jobs():
    """List all jobs with optional status filter"""
    status_filter = request.args.get('status')
    
    filtered_jobs = []
    for job in jobs.values():
        if status_filter and job['status'] != status_filter:
            continue
        filtered_jobs.append(job)
    
    return jsonify({
        'total': len(filtered_jobs),
        'jobs': filtered_jobs
    })


# ============================================================================
# Helper Functions
# ============================================================================

def get_tailscale_ip():
    """Get the Tailscale IP address"""
    try:
        hostname = socket.gethostname()
        ip = socket.gethostbyname(hostname)
        return ip
    except:
        return "100.124.226.72"  # Default fallback


def run_event_loop():
    """Run the global event loop in a background thread"""
    global global_loop
    global_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(global_loop)
    global_loop.run_forever()


# ============================================================================
# Startup & Shutdown
# ============================================================================

def startup():
    """Initialize browser and start event loop"""
    global loop_thread
    
    tailscale_ip = get_tailscale_ip()
    print(f"📍 Tailscale IP: {tailscale_ip}")
    print(f"🌐 Access from K8s: http://{tailscale_ip}:8000")
    print()
    
    # Start event loop in background thread
    print("🔧 Starting global event loop in background thread...")
    loop_thread = Thread(target=run_event_loop, daemon=True)
    loop_thread.start()
    
    # Wait a bit for loop to start
    import time
    time.sleep(0.5)
    print("✅ Event loop started!")
    
    # Initialize browser in the event loop
    future = asyncio.run_coroutine_threadsafe(initialize_browser(), global_loop)
    future.result(timeout=30)
    print("✅ Startup complete!")


if __name__ == '__main__':
    startup()
    
    try:
        app.run(host='0.0.0.0', port=8000, debug=False)
    finally:
        # Cleanup on shutdown
        print("\n🛑 Shutting down...")
        if global_loop and global_loop.is_running():
            # Close browser in the global loop
            future = asyncio.run_coroutine_threadsafe(close_browser(), global_loop)
            future.result(timeout=10)
            
            # Stop the event loop
            global_loop.call_soon_threadsafe(global_loop.stop)
            loop_thread.join(timeout=5)
        
        print("✅ Shutdown complete!")

