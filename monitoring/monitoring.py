"""
FACEIT Telegram Bot Monitoring Dashboard
Simple and effective monitoring system for all bot services
"""

import os
import json
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any
from collections import defaultdict, deque

import redis
import asyncpg
from flask import Flask, render_template, jsonify
from flask_cors import CORS
from apscheduler.schedulers.background import BackgroundScheduler

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

# Configuration from environment
REDIS_URL = 'rediss://default:AZn7AAIncDFmZDE2ZDI4YTQ3Y2I0OWVkYTZjYjkzYWQ5OTIzNWRiMHAxMzk0MTk@enjoyed-tick-39419.upstash.io:6379/0'
DATABASE_URL = os.getenv('DATABASE_URL', '').replace('+asyncpg', '')
MONITORING_PORT = int(os.getenv('MONITORING_PORT', '9181'))

# Parse Redis URL for SSL support
if REDIS_URL.startswith('rediss://'):
    redis_client = redis.from_url(REDIS_URL, ssl_cert_reqs=None)
else:
    redis_client = redis.from_url(REDIS_URL)

# Metrics storage (in-memory for simplicity)
metrics_store = {
    'requests_hourly': defaultdict(int),  # Hour -> count
    'requests_by_command': defaultdict(int),  # Command -> count
    'active_users': set(),  # Set of active user IDs
    'total_users': 0,
    'service_status': {},
    'queue_stats': {},
    'errors': deque(maxlen=100),  # Last 100 errors
    'response_times': deque(maxlen=1000),  # Last 1000 response times
    'user_requests': defaultdict(int),  # User ID -> request count
}

# Background scheduler for metrics collection
scheduler = BackgroundScheduler()


async def check_postgresql():
    """Check PostgreSQL connection status"""
    try:
        if not DATABASE_URL:
            return {'status': 'not_configured', 'error': 'No DATABASE_URL'}
        
        conn = await asyncpg.connect(DATABASE_URL, command_timeout=5)
        version = await conn.fetchval('SELECT version()')
        
        # Get database statistics
        db_size = await conn.fetchval("""
            SELECT pg_size_pretty(pg_database_size(current_database()))
        """)
        
        connections = await conn.fetchval("""
            SELECT count(*) FROM pg_stat_activity 
            WHERE datname = current_database()
        """)
        
        # Get user statistics if table exists
        try:
            total_users = await conn.fetchval("""
                SELECT COUNT(DISTINCT user_id) FROM users
            """)
            
            active_today = await conn.fetchval("""
                SELECT COUNT(DISTINCT user_id) FROM users 
                WHERE last_seen >= CURRENT_DATE
            """)
            
            user_stats = {
                'total': total_users or 0,
                'active_today': active_today or 0
            }
        except:
            user_stats = {'total': 0, 'active_today': 0}
        
        await conn.close()
        
        return {
            'status': 'healthy',
            'version': version.split()[0] if version else 'Unknown',
            'database_size': db_size,
            'connections': connections,
            'users': user_stats
        }
    except Exception as e:
        logger.error(f"PostgreSQL check failed: {e}")
        return {'status': 'error', 'error': str(e)}


async def check_redis():
    """Check Redis connection and get queue statistics"""
    try:
        # Test connection
        redis_client.ping()
        
        # Get Redis info
        info = redis_client.info()
        
        # Get queue lengths
        queues = {
            'high': redis_client.llen('rq:queue:high'),
            'default': redis_client.llen('rq:queue:default'),
            'low': redis_client.llen('rq:queue:low'),
            'failed': redis_client.zcard('rq:failed'),
        }
        
        # Get worker info
        workers = []
        for key in redis_client.keys('rq:worker:*'):
            worker_data = redis_client.hgetall(key)
            if worker_data:
                workers.append({
                    'name': key.decode().split(':')[-1],
                    'state': worker_data.get(b'state', b'unknown').decode(),
                    'current_job': worker_data.get(b'current_job', b'').decode()
                })
        
        return {
            'status': 'healthy',
            'version': info.get('redis_version', 'Unknown'),
            'memory_used': info.get('used_memory_human', 'Unknown'),
            'connected_clients': info.get('connected_clients', 0),
            'queues': queues,
            'workers': workers
        }
    except Exception as e:
        logger.error(f"Redis check failed: {e}")
        return {'status': 'error', 'error': str(e)}


def collect_metrics():
    """Collect metrics from Redis and database"""
    try:
        # Get current hour
        current_hour = datetime.now().strftime('%Y-%m-%d %H:00')
        
        # Try to get metrics from Redis
        try:
            # Get request count for current hour
            hour_key = f"metrics:requests:{current_hour}"
            count = redis_client.get(hour_key)
            if count:
                metrics_store['requests_hourly'][current_hour] = int(count)
            
            # Get command statistics
            for cmd in ['start', 'setplayer', 'analyze', 'profile', 'stats', 'matches', 'subscription']:
                cmd_key = f"metrics:command:{cmd}"
                count = redis_client.get(cmd_key)
                if count:
                    metrics_store['requests_by_command'][cmd] = int(count)
            
            # Get active users
            active_key = f"metrics:users:active:{datetime.now().strftime('%Y-%m-%d')}"
            active_users = redis_client.smembers(active_key)
            if active_users:
                metrics_store['active_users'] = {u.decode() for u in active_users}
        except Exception as e:
            logger.warning(f"Could not get metrics from Redis: {e}")
        
        # Check service health
        asyncio.run(update_service_status())
        
    except Exception as e:
        logger.error(f"Metrics collection failed: {e}")


async def update_service_status():
    """Update status of all services"""
    metrics_store['service_status'] = {
        'postgresql': await check_postgresql(),
        'redis': await check_redis(),
        'timestamp': datetime.now().isoformat()
    }


async def check_docker_services():
    """Check Docker container status"""
    try:
        import docker
        client = docker.from_env()
        
        services = {}
        for container in client.containers.list():
            if 'faceit' in container.name:
                services[container.name] = {
                    'status': container.status,
                    'health': container.health if hasattr(container, 'health') else 'unknown',
                    'started': container.attrs['State']['StartedAt']
                }
        
        return services
    except:
        return {}


@app.route('/')
def dashboard():
    """Main dashboard page"""
    return render_template('dashboard.html')


@app.route('/api/metrics')
def get_metrics():
    """API endpoint for metrics data"""
    # Prepare hourly data for last 24 hours
    hourly_data = []
    now = datetime.now()
    for i in range(24):
        hour = (now - timedelta(hours=i)).strftime('%Y-%m-%d %H:00')
        hourly_data.append({
            'hour': hour.split()[-1],
            'count': metrics_store['requests_hourly'].get(hour, 0)
        })
    hourly_data.reverse()
    
    # Get top users
    top_users = sorted(
        metrics_store['user_requests'].items(), 
        key=lambda x: x[1], 
        reverse=True
    )[:10]
    
    # Calculate average response time
    avg_response_time = 0
    if metrics_store['response_times']:
        avg_response_time = sum(metrics_store['response_times']) / len(metrics_store['response_times'])
    
    return jsonify({
        'service_status': metrics_store['service_status'],
        'hourly_requests': hourly_data,
        'command_stats': dict(metrics_store['requests_by_command']),
        'user_stats': {
            'total': metrics_store['total_users'],
            'active_today': len(metrics_store['active_users']),
            'top_users': [{'user_id': u[0], 'requests': u[1]} for u in top_users]
        },
        'queue_stats': metrics_store['service_status'].get('redis', {}).get('queues', {}),
        'workers': metrics_store['service_status'].get('redis', {}).get('workers', []),
        'performance': {
            'avg_response_time': round(avg_response_time, 2),
            'errors_count': len(metrics_store['errors'])
        },
        'last_updated': datetime.now().isoformat()
    })


@app.route('/api/health')
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat()
    })


@app.route('/api/errors')
def get_errors():
    """Get recent errors"""
    return jsonify({
        'errors': list(metrics_store['errors']),
        'count': len(metrics_store['errors'])
    })


def start_monitoring():
    """Start the monitoring service"""
    # Initial metrics collection
    collect_metrics()
    
    # Schedule periodic metrics collection
    scheduler.add_job(
        func=collect_metrics,
        trigger="interval",
        seconds=60,
        id='collect_metrics',
        replace_existing=True
    )
    
    scheduler.start()
    
    # Start Flask app
    logger.info(f"Starting monitoring dashboard on port {MONITORING_PORT}")
    app.run(host='0.0.0.0', port=MONITORING_PORT, debug=False)


if __name__ == '__main__':
    try:
        start_monitoring()
    except KeyboardInterrupt:
        logger.info("Monitoring dashboard stopped")
        scheduler.shutdown()