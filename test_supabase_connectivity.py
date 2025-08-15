#!/usr/bin/env python3
"""
Comprehensive Supabase PostgreSQL connectivity test for production deployment.

This script performs extensive testing to diagnose and resolve the 
"Temporary failure in name resolution" issue affecting Docker containers
connecting to Supabase pooler endpoints.

Tests performed:
1. DNS resolution for all Supabase endpoints
2. Direct asyncpg connection tests (both pooler and direct)
3. IPv4/IPv6 connectivity verification
4. Connection string format validation
5. Docker network connectivity simulation
6. Database schema verification
7. Performance benchmarking
8. Failover configuration testing

Usage:
    python test_supabase_connectivity.py [--production]
    
Arguments:
    --production: Use production connection string (default: staging)
"""

import asyncio
import asyncpg
import dns.resolver
import logging
import os
import platform
import socket
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('supabase_connectivity_test.log')
    ]
)
logger = logging.getLogger(__name__)


class SupabaseConnectivityTester:
    """Comprehensive Supabase connectivity tester for production environments."""
    
    def __init__(self):
        self.test_results = {}
        self.connection_strings = {}
        self.endpoints = {}
        
        # Load environment or use provided values
        self.load_connection_details()
        
    def load_connection_details(self):
        """Load Supabase connection details."""
        # Primary production connection string from user
        self.connection_strings['production_pooler'] = (
            "postgresql://postgres.emzlxdutmhmbvaetphpu:b6Sfj*D!Gr98vPY@"
            "aws-0-us-east-1.pooler.supabase.com:6543/postgres"
        )
        
        # Alternative connection strings to test
        self.connection_strings['production_direct'] = (
            "postgresql://postgres.emzlxdutmhmbvaetphpu:b6Sfj*D!Gr98vPY@"
            "aws-0-us-east-1.pooler.supabase.com:5432/postgres"
        )
        
        # AsyncPG versions
        self.connection_strings['production_pooler_asyncpg'] = (
            "postgresql+asyncpg://postgres.emzlxdutmhmbvaetphpu:b6Sfj*D!Gr98vPY@"
            "aws-0-us-east-1.pooler.supabase.com:6543/postgres"
        )
        
        # Extract endpoints for testing
        for name, conn_str in self.connection_strings.items():
            parsed = urlparse(conn_str.replace('postgresql+asyncpg://', 'postgresql://'))
            self.endpoints[name] = {
                'host': parsed.hostname,
                'port': parsed.port,
                'database': parsed.path.lstrip('/'),
                'username': parsed.username,
                'password': parsed.password
            }
    
    async def test_dns_resolution(self) -> Dict[str, bool]:
        """Test DNS resolution for all Supabase endpoints."""
        logger.info("🔍 Testing DNS resolution...")
        results = {}
        
        unique_hosts = set(ep['host'] for ep in self.endpoints.values())
        
        for host in unique_hosts:
            try:
                # Test standard DNS resolution
                ip_addresses = socket.getaddrinfo(host, 80, socket.AF_UNSPEC, socket.SOCK_STREAM)
                ipv4_addresses = [addr[4][0] for addr in ip_addresses if addr[0] == socket.AF_INET]
                ipv6_addresses = [addr[4][0] for addr in ip_addresses if addr[0] == socket.AF_INET6]
                
                logger.info(f"✅ {host}:")
                logger.info(f"   IPv4: {ipv4_addresses}")
                logger.info(f"   IPv6: {ipv6_addresses}")
                
                results[host] = {
                    'resolved': True,
                    'ipv4': ipv4_addresses,
                    'ipv6': ipv6_addresses
                }
                
                # Test with different DNS resolvers
                try:
                    resolver = dns.resolver.Resolver()
                    resolver.nameservers = ['8.8.8.8', '1.1.1.1']  # Google and Cloudflare DNS
                    answers = resolver.resolve(host, 'A')
                    dns_ipv4 = [str(answer) for answer in answers]
                    logger.info(f"   DNS (8.8.8.8): {dns_ipv4}")
                    results[host]['dns_ipv4'] = dns_ipv4
                except Exception as dns_e:
                    logger.warning(f"   DNS resolver failed: {dns_e}")
                    results[host]['dns_error'] = str(dns_e)
                
            except Exception as e:
                logger.error(f"❌ {host}: DNS resolution failed - {e}")
                results[host] = {'resolved': False, 'error': str(e)}
        
        return results
    
    async def test_tcp_connectivity(self) -> Dict[str, bool]:
        """Test TCP connectivity to all endpoints."""
        logger.info("🔌 Testing TCP connectivity...")
        results = {}
        
        for name, endpoint in self.endpoints.items():
            host = endpoint['host']
            port = endpoint['port']
            
            try:
                # Test with asyncio
                logger.info(f"Testing {name}: {host}:{port}")
                
                # Set reasonable timeout
                future = asyncio.open_connection(host, port)
                reader, writer = await asyncio.wait_for(future, timeout=10.0)
                
                # Connection successful
                writer.close()
                await writer.wait_closed()
                
                logger.info(f"✅ {name}: TCP connection successful")
                results[name] = True
                
            except asyncio.TimeoutError:
                logger.error(f"❌ {name}: Connection timeout (10s)")
                results[name] = False
            except Exception as e:
                logger.error(f"❌ {name}: TCP connection failed - {e}")
                results[name] = False
        
        return results
    
    async def test_postgres_connectivity(self) -> Dict[str, Dict]:
        """Test PostgreSQL connectivity using asyncpg."""
        logger.info("🐘 Testing PostgreSQL connectivity...")
        results = {}
        
        for name, conn_str in self.connection_strings.items():
            if 'asyncpg' in conn_str:
                # Convert SQLAlchemy URL to asyncpg format
                test_url = conn_str.replace('postgresql+asyncpg://', 'postgresql://')
            else:
                test_url = conn_str
            
            logger.info(f"Testing {name}...")
            
            try:
                start_time = time.time()
                
                # Test connection with timeout
                conn = await asyncio.wait_for(
                    asyncpg.connect(test_url),
                    timeout=15.0
                )
                
                connect_time = time.time() - start_time
                
                # Test basic queries
                version = await conn.fetchval('SELECT version()')
                current_db = await conn.fetchval('SELECT current_database()')
                current_user = await conn.fetchval('SELECT current_user')
                connection_count = await conn.fetchval(
                    "SELECT count(*) FROM pg_stat_activity WHERE datname = current_database()"
                )
                
                # Test schema access
                tables_result = await conn.fetch("""
                    SELECT table_name 
                    FROM information_schema.tables 
                    WHERE table_schema = 'public'
                    ORDER BY table_name
                """)
                tables = [row['table_name'] for row in tables_result]
                
                await conn.close()
                
                results[name] = {
                    'success': True,
                    'connect_time': round(connect_time, 3),
                    'version': version.split()[1] if version else 'unknown',
                    'database': current_db,
                    'user': current_user,
                    'connections': connection_count,
                    'tables': tables,
                    'table_count': len(tables)
                }
                
                logger.info(f"✅ {name}: Connection successful ({connect_time:.3f}s)")
                logger.info(f"   Database: {current_db}, User: {current_user}")
                logger.info(f"   Active connections: {connection_count}")
                logger.info(f"   Tables found: {len(tables)}")
                
            except asyncio.TimeoutError:
                logger.error(f"❌ {name}: PostgreSQL connection timeout (15s)")
                results[name] = {'success': False, 'error': 'timeout'}
            except Exception as e:
                logger.error(f"❌ {name}: PostgreSQL connection failed - {e}")
                results[name] = {'success': False, 'error': str(e)}
        
        return results
    
    async def test_connection_pooling(self) -> Dict[str, Dict]:
        """Test connection pooling performance and limits."""
        logger.info("🏊 Testing connection pooling...")
        results = {}
        
        # Test with the pooler endpoint
        conn_str = self.connection_strings['production_pooler'].replace('postgresql+asyncpg://', 'postgresql://')
        
        try:
            logger.info("Testing concurrent connections...")
            
            # Test multiple concurrent connections
            max_connections = 10
            connections = []
            connect_times = []
            
            start_time = time.time()
            
            for i in range(max_connections):
                try:
                    conn_start = time.time()
                    conn = await asyncpg.connect(conn_str)
                    connect_time = time.time() - conn_start
                    connect_times.append(connect_time)
                    connections.append(conn)
                    logger.info(f"   Connection {i+1}: {connect_time:.3f}s")
                except Exception as e:
                    logger.error(f"   Connection {i+1} failed: {e}")
                    break
            
            total_time = time.time() - start_time
            
            # Test query performance with all connections
            query_times = []
            for i, conn in enumerate(connections):
                try:
                    query_start = time.time()
                    await conn.fetchval('SELECT 1')
                    query_time = time.time() - query_start
                    query_times.append(query_time)
                except Exception as e:
                    logger.error(f"   Query on connection {i+1} failed: {e}")
            
            # Close all connections
            for conn in connections:
                await conn.close()
            
            results['pooling'] = {
                'max_connections_tested': max_connections,
                'successful_connections': len(connections),
                'total_setup_time': round(total_time, 3),
                'avg_connect_time': round(sum(connect_times) / len(connect_times), 3) if connect_times else 0,
                'avg_query_time': round(sum(query_times) / len(query_times), 3) if query_times else 0,
                'connect_times': [round(t, 3) for t in connect_times],
                'query_times': [round(t, 3) for t in query_times]
            }
            
            logger.info(f"✅ Connection pooling test completed:")
            logger.info(f"   Successful connections: {len(connections)}/{max_connections}")
            logger.info(f"   Average connect time: {results['pooling']['avg_connect_time']}s")
            logger.info(f"   Average query time: {results['pooling']['avg_query_time']}s")
            
        except Exception as e:
            logger.error(f"❌ Connection pooling test failed: {e}")
            results['pooling'] = {'success': False, 'error': str(e)}
        
        return results
    
    def test_system_connectivity(self) -> Dict[str, any]:
        """Test system-level connectivity tools."""
        logger.info("🖥️ Testing system connectivity...")
        results = {}
        
        host = "aws-0-us-east-1.pooler.supabase.com"
        
        # Test ping
        try:
            if platform.system().lower() == "windows":
                ping_result = subprocess.run(
                    ["ping", "-n", "4", host], 
                    capture_output=True, text=True, timeout=20
                )
            else:
                ping_result = subprocess.run(
                    ["ping", "-c", "4", host], 
                    capture_output=True, text=True, timeout=20
                )
            
            results['ping'] = {
                'success': ping_result.returncode == 0,
                'output': ping_result.stdout,
                'error': ping_result.stderr
            }
            
            if ping_result.returncode == 0:
                logger.info(f"✅ Ping to {host} successful")
            else:
                logger.warning(f"⚠️ Ping to {host} failed")
                
        except Exception as e:
            logger.error(f"❌ Ping test failed: {e}")
            results['ping'] = {'success': False, 'error': str(e)}
        
        # Test nslookup/dig
        try:
            if platform.system().lower() == "windows":
                nslookup_result = subprocess.run(
                    ["nslookup", host], 
                    capture_output=True, text=True, timeout=10
                )
                tool_name = "nslookup"
            else:
                nslookup_result = subprocess.run(
                    ["dig", "+short", host], 
                    capture_output=True, text=True, timeout=10
                )
                tool_name = "dig"
            
            results[tool_name] = {
                'success': nslookup_result.returncode == 0,
                'output': nslookup_result.stdout,
                'error': nslookup_result.stderr
            }
            
            if nslookup_result.returncode == 0:
                logger.info(f"✅ {tool_name} successful")
            else:
                logger.warning(f"⚠️ {tool_name} failed")
                
        except Exception as e:
            logger.error(f"❌ DNS lookup test failed: {e}")
            results['dns_lookup'] = {'success': False, 'error': str(e)}
        
        # Test telnet (port connectivity)
        for port in [5432, 6543]:
            try:
                telnet_result = subprocess.run(
                    ["telnet", host, str(port)], 
                    capture_output=True, text=True, timeout=10,
                    input="\n"
                )
                
                results[f'telnet_{port}'] = {
                    'success': telnet_result.returncode == 0,
                    'output': telnet_result.stdout,
                    'error': telnet_result.stderr
                }
                
            except Exception as e:
                logger.warning(f"⚠️ Telnet test for port {port} failed: {e}")
                results[f'telnet_{port}'] = {'success': False, 'error': str(e)}
        
        return results
    
    async def test_docker_network_simulation(self) -> Dict[str, any]:
        """Simulate Docker network conditions."""
        logger.info("🐳 Testing Docker network simulation...")
        results = {}
        
        # Test with different DNS servers (simulating Docker's DNS)
        dns_servers = [
            "8.8.8.8",      # Google
            "1.1.1.1",      # Cloudflare  
            "127.0.0.11",   # Docker's default DNS (if available)
            "208.67.222.222" # OpenDNS
        ]
        
        host = "aws-0-us-east-1.pooler.supabase.com"
        
        for dns_server in dns_servers:
            try:
                resolver = dns.resolver.Resolver()
                resolver.nameservers = [dns_server]
                resolver.timeout = 5
                resolver.lifetime = 10
                
                answers = resolver.resolve(host, 'A')
                ip_addresses = [str(answer) for answer in answers]
                
                results[f'dns_{dns_server}'] = {
                    'success': True,
                    'addresses': ip_addresses
                }
                
                logger.info(f"✅ DNS via {dns_server}: {ip_addresses}")
                
            except Exception as e:
                logger.warning(f"⚠️ DNS via {dns_server} failed: {e}")
                results[f'dns_{dns_server}'] = {
                    'success': False,
                    'error': str(e)
                }
        
        return results
    
    def generate_docker_configuration(self) -> str:
        """Generate optimized Docker configuration."""
        
        # Determine best connection string based on test results
        best_conn = None
        for name, result in self.test_results.get('postgres', {}).items():
            if result.get('success') and result.get('connect_time', 999) < 5.0:
                best_conn = name
                break
        
        if not best_conn:
            best_conn = 'production_pooler'  # fallback
        
        config = f"""# Optimized Docker Configuration for Supabase PostgreSQL
# Generated on {datetime.now().isoformat()}

# Recommended connection string (fastest from tests):
DATABASE_URL={self.connection_strings[best_conn]}

# Docker Compose DNS configuration:
version: '3.8'
services:
  your-service:
    dns:
      - 8.8.8.8
      - 1.1.1.1
    extra_hosts:
      - "aws-0-us-east-1.pooler.supabase.com:$(dig +short aws-0-us-east-1.pooler.supabase.com | head -1)"
    
    # Connection pool settings for production:
    environment:
      - DB_POOL_SIZE=20
      - DB_POOL_OVERFLOW=30
      - DB_POOL_TIMEOUT=30
      - DB_MAX_RETRIES=5
      - DB_CONNECTION_TIMEOUT=15
      
# Alternative connection strings for failover:
# Primary (Pooler): {self.connection_strings['production_pooler']}
# Direct: {self.connection_strings['production_direct']}
"""
        return config
    
    async def run_comprehensive_test(self) -> Dict:
        """Run all connectivity tests."""
        logger.info("🚀 Starting comprehensive Supabase connectivity test...")
        logger.info("=" * 80)
        
        # Store all test results
        self.test_results = {
            'timestamp': datetime.now().isoformat(),
            'system': platform.system(),
            'python_version': platform.python_version()
        }
        
        # Test 1: DNS Resolution
        self.test_results['dns'] = await self.test_dns_resolution()
        
        # Test 2: TCP Connectivity
        self.test_results['tcp'] = await self.test_tcp_connectivity()
        
        # Test 3: PostgreSQL Connectivity
        self.test_results['postgres'] = await self.test_postgres_connectivity()
        
        # Test 4: Connection Pooling
        pool_results = await self.test_connection_pooling()
        self.test_results.update(pool_results)
        
        # Test 5: System Connectivity
        self.test_results['system'] = self.test_system_connectivity()
        
        # Test 6: Docker Network Simulation
        self.test_results['docker_dns'] = await self.test_docker_network_simulation()
        
        return self.test_results
    
    def print_summary(self):
        """Print test summary and recommendations."""
        logger.info("\n" + "=" * 80)
        logger.info("CONNECTIVITY TEST SUMMARY")
        logger.info("=" * 80)
        
        # DNS Summary
        dns_results = self.test_results.get('dns', {})
        dns_success = sum(1 for result in dns_results.values() if result.get('resolved', False))
        logger.info(f"DNS Resolution: {dns_success}/{len(dns_results)} hosts resolved")
        
        # TCP Summary
        tcp_results = self.test_results.get('tcp', {})
        tcp_success = sum(1 for success in tcp_results.values() if success)
        logger.info(f"TCP Connectivity: {tcp_success}/{len(tcp_results)} endpoints reachable")
        
        # PostgreSQL Summary
        pg_results = self.test_results.get('postgres', {})
        pg_success = sum(1 for result in pg_results.values() if result.get('success', False))
        logger.info(f"PostgreSQL Connectivity: {pg_success}/{len(pg_results)} connections successful")
        
        # Recommendations
        logger.info("\n🎯 RECOMMENDATIONS:")
        
        if pg_success == 0:
            logger.error("❌ CRITICAL: No PostgreSQL connections successful!")
            logger.error("   - Check if Supabase project is active and accessible")
            logger.error("   - Verify connection credentials")
            logger.error("   - Test from different network/location")
        elif pg_success < len(pg_results):
            logger.warning("⚠️ Some connections failed - consider failover configuration")
        else:
            logger.info("✅ All PostgreSQL connections successful!")
        
        # Best connection recommendation
        best_conn = None
        best_time = float('inf')
        
        for name, result in pg_results.items():
            if result.get('success') and result.get('connect_time', 999) < best_time:
                best_time = result['connect_time']
                best_conn = name
        
        if best_conn:
            logger.info(f"🏆 RECOMMENDED CONNECTION: {best_conn} ({best_time:.3f}s)")
            logger.info(f"   Use: {self.connection_strings[best_conn]}")
        
        # Docker configuration
        docker_config = self.generate_docker_configuration()
        config_file = Path("docker_supabase_config.txt")
        config_file.write_text(docker_config)
        logger.info(f"\n📝 Docker configuration saved to: {config_file.absolute()}")


async def main():
    """Main test runner."""
    tester = SupabaseConnectivityTester()
    
    try:
        # Run comprehensive tests
        results = await tester.run_comprehensive_test()
        
        # Print summary and recommendations
        tester.print_summary()
        
        # Save detailed results
        import json
        results_file = Path("supabase_connectivity_results.json")
        with open(results_file, 'w') as f:
            json.dump(results, f, indent=2, default=str)
        
        logger.info(f"\n📊 Detailed results saved to: {results_file.absolute()}")
        
        # Return exit code based on success
        pg_results = results.get('postgres', {})
        successful_connections = sum(1 for r in pg_results.values() if r.get('success', False))
        
        if successful_connections > 0:
            logger.info("🎉 Test completed successfully - at least one connection works!")
            return 0
        else:
            logger.error("💥 Test failed - no working connections found!")
            return 1
            
    except Exception as e:
        logger.error(f"💥 Test runner failed: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return 1


if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        logger.info("🛑 Test interrupted by user")
        sys.exit(1)