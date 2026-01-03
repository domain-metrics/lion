#!/usr/bin/env python3
"""
Test script to demonstrate the queue system
Submits 5 domains and shows they process one at a time
"""

import requests
import time
import json

SERVER_URL = "http://127.0.0.1:8000"

def submit_batch_and_monitor():
    """Submit a batch and monitor the queue"""
    
    # Submit batch of 5 domains
    print("📦 Submitting batch of 5 domains...\n")
    
    response = requests.post(
        f"{SERVER_URL}/batch",
        json={
            'domains': [
                'techcrunch.com',
                'example.com', 
                'github.com',
                'stackoverflow.com',
                'reddit.com',
                'elmleynaturereserve.co.uk',
                'aooke-anime.com',
                'freetronics.com.au',
                'roell.net',
                'tongitsfun.xyz',
                'autoeurope.eu',
                'thecarbonunderground.org',
                'speedgoat.com',
                'hotelunique.com',
                'shareindia.com',
                'techcrunch.com',
                'example.com', 
                'github.com',
                'stackoverflow.com',
                'reddit.com',
                'elmleynaturereserve.co.uk',
                'aooke-anime.com',
                'freetronics.com.au',
                'roell.net',
                'tongitsfun.xyz',
                'autoeurope.eu',
                'thecarbonunderground.org',
                'speedgoat.com',
                'hotelunique.com',
                'shareindia.com',
                'techcrunch.com',
                'example.com', 
                'github.com',
                'stackoverflow.com',
                'reddit.com',
                'elmleynaturereserve.co.uk',
                'aooke-anime.com',
                'freetronics.com.au',
                'roell.net',
                'tongitsfun.xyz',
                'autoeurope.eu',
                'thecarbonunderground.org',
                'speedgoat.com',
                'hotelunique.com',
                'shareindia.com',
                'techcrunch.com',
                'example.com', 
                'github.com',
                'stackoverflow.com',
                'reddit.com',
                'elmleynaturereserve.co.uk',
                'aooke-anime.com',
                'freetronics.com.au',
                'roell.net',
                'tongitsfun.xyz',
                'autoeurope.eu',
                'thecarbonunderground.org',
                'speedgoat.com',
                'hotelunique.com',
                'shareindia.com',
            ]
        }
    )
    
    result = response.json()
    print(f"✅ {result['message']}")
    print(f"Task IDs: {result['task_ids'][:2]}... ({len(result['task_ids'])} total)\n")
    
    task_ids = result['task_ids']
    
    # Monitor queue and job status
    print("📊 Monitoring queue (press Ctrl+C to stop)...\n")
    print("-" * 80)
    
    try:
        while True:
            # Get queue status
            queue_resp = requests.get(f"{SERVER_URL}/queue")
            queue_data = queue_resp.json()
            
            # Get health/stats
            health_resp = requests.get(f"{SERVER_URL}/health")
            health_data = health_resp.json()
            
            # Clear previous output (optional)
            print(f"\r📊 Queue: {queue_data['queue_size']} | " +
                  f"Processing: {health_data['processing']} | " +
                  f"Queued: {health_data['queued']} | " +
                  f"Completed: {health_data['completed']} | " +
                  f"Failed: {health_data['failed']}", end="")
            
            # Check if all done
            if health_data['completed'] + health_data['failed'] >= len(task_ids):
                print("\n\n✅ All tasks completed!")
                break
            
            time.sleep(2)
    
    except KeyboardInterrupt:
        print("\n\n⏸️  Monitoring stopped\n")
    
    # Show final results
    print("\n" + "=" * 80)
    print("📋 FINAL RESULTS")
    print("=" * 80 + "\n")
    
    for i, task_id in enumerate(task_ids):
        result_resp = requests.get(f"{SERVER_URL}/result/{task_id}")
        result_data = result_resp.json()
        
        status = result_data['status']
        domain = result_data['domain']
        
        status_icon = "✅" if status == "completed" else "❌" if status == "failed" else "⏳"
        print(f"{status_icon} {domain}: {status}")
        
        if status == "completed" and 'result' in result_data:
            metrics = result_data['result']
            print(f"   DR: {metrics.get('_dr')}, " +
                  f"Backlinks: {metrics.get('backlinks')}, " +
                  f"Linking: {metrics.get('linking_websites')}")
        elif status == "failed":
            print(f"   Error: {result_data.get('error', 'Unknown error')}")
        
        print()


def demo_queue_behavior():
    """Demonstrate queue behavior"""
    
    submit_batch_and_monitor()


if __name__ == '__main__':
    start_time = time.time()
    demo_queue_behavior()
    end_time = time.time()
    print(f"Time taken: {end_time - start_time} seconds")

