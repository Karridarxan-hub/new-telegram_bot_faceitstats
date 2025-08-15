#!/bin/bash
# VPS Supabase Connectivity Test Script
# Run this script on the VPS to diagnose database connectivity issues

set -e

echo "🚀 VPS Supabase Connectivity Test"
echo "=================================="
echo "Timestamp: $(date)"
echo "Host: $(hostname)"
echo "IP: $(curl -s ifconfig.me 2>/dev/null || echo 'Unable to determine')"
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Supabase connection details
SUPABASE_HOST="aws-0-us-east-1.pooler.supabase.com"
SUPABASE_POOLER_PORT="6543"
SUPABASE_DIRECT_PORT="5432"
SUPABASE_PROJECT="emzlxdutmhmbvaetphpu"

echo "📋 Connection Details:"
echo "   Host: $SUPABASE_HOST"
echo "   Pooler Port: $SUPABASE_POOLER_PORT"
echo "   Direct Port: $SUPABASE_DIRECT_PORT"
echo "   Project: $SUPABASE_PROJECT"
echo ""

# Test 1: Basic System Info
echo -e "${BLUE}🖥️ System Information${NC}"
echo "OS: $(cat /etc/os-release | grep PRETTY_NAME | cut -d'=' -f2 | tr -d '\"')"
echo "Kernel: $(uname -r)"
echo "Architecture: $(uname -m)"
echo "DNS Config:"
cat /etc/resolv.conf | grep nameserver | head -3
echo ""

# Test 2: DNS Resolution
echo -e "${BLUE}🔍 DNS Resolution Tests${NC}"

# Test with system resolver
echo "Testing with system resolver..."
if nslookup $SUPABASE_HOST > /dev/null 2>&1; then
    echo -e "${GREEN}✅ System DNS resolution successful${NC}"
    nslookup $SUPABASE_HOST | grep "Address:" | tail -n +2
else
    echo -e "${RED}❌ System DNS resolution failed${NC}"
fi

# Test with different DNS servers
for dns_server in "8.8.8.8" "1.1.1.1" "208.67.222.222"; do
    echo "Testing with DNS server $dns_server..."
    if nslookup $SUPABASE_HOST $dns_server > /dev/null 2>&1; then
        echo -e "${GREEN}✅ DNS via $dns_server successful${NC}"
    else
        echo -e "${RED}❌ DNS via $dns_server failed${NC}"
    fi
done

# Test with dig if available
if command -v dig &> /dev/null; then
    echo "Using dig for detailed DNS info..."
    dig +short $SUPABASE_HOST A
    dig +short $SUPABASE_HOST AAAA
fi
echo ""

# Test 3: Network Connectivity
echo -e "${BLUE}🔌 Network Connectivity Tests${NC}"

# Ping test
echo "Testing ping connectivity..."
if ping -c 4 $SUPABASE_HOST > /dev/null 2>&1; then
    echo -e "${GREEN}✅ Ping successful${NC}"
    ping -c 4 $SUPABASE_HOST | tail -1
else
    echo -e "${RED}❌ Ping failed${NC}"
fi

# Port connectivity tests
for port in $SUPABASE_DIRECT_PORT $SUPABASE_POOLER_PORT; do
    echo "Testing TCP connection to port $port..."
    if timeout 10 bash -c "</dev/tcp/$SUPABASE_HOST/$port" 2>/dev/null; then
        echo -e "${GREEN}✅ Port $port is reachable${NC}"
    else
        echo -e "${RED}❌ Port $port is not reachable${NC}"
    fi
done

# Test with netcat if available
if command -v nc &> /dev/null; then
    for port in $SUPABASE_DIRECT_PORT $SUPABASE_POOLER_PORT; do
        echo "Testing with netcat on port $port..."
        if timeout 5 nc -z $SUPABASE_HOST $port; then
            echo -e "${GREEN}✅ Netcat to port $port successful${NC}"
        else
            echo -e "${RED}❌ Netcat to port $port failed${NC}"
        fi
    done
fi
echo ""

# Test 4: Route and Network Path
echo -e "${BLUE}🛣️ Network Path Analysis${NC}"

if command -v traceroute &> /dev/null; then
    echo "Traceroute to $SUPABASE_HOST (first 10 hops):"
    timeout 30 traceroute -m 10 $SUPABASE_HOST 2>/dev/null || echo "Traceroute failed or timed out"
elif command -v tracepath &> /dev/null; then
    echo "Tracepath to $SUPABASE_HOST:"
    timeout 30 tracepath $SUPABASE_HOST 2>/dev/null || echo "Tracepath failed or timed out"
else
    echo "No traceroute tool available"
fi
echo ""

# Test 5: PostgreSQL Connection Test
echo -e "${BLUE}🐘 PostgreSQL Connection Tests${NC}"

# Check if psql is available
if command -v psql &> /dev/null; then
    echo "Testing with psql..."
    
    # Test pooler connection
    POOLER_URL="postgresql://postgres.${SUPABASE_PROJECT}:b6Sfj*D!Gr98vPY@${SUPABASE_HOST}:${SUPABASE_POOLER_PORT}/postgres"
    echo "Testing pooler connection..."
    if timeout 15 psql "$POOLER_URL" -c "SELECT version();" > /dev/null 2>&1; then
        echo -e "${GREEN}✅ Pooler connection successful${NC}"
        psql "$POOLER_URL" -c "SELECT current_database(), current_user, NOW();"
    else
        echo -e "${RED}❌ Pooler connection failed${NC}"
    fi
    
    # Test direct connection
    DIRECT_URL="postgresql://postgres.${SUPABASE_PROJECT}:b6Sfj*D!Gr98vPY@${SUPABASE_HOST}:${SUPABASE_DIRECT_PORT}/postgres"
    echo "Testing direct connection..."
    if timeout 15 psql "$DIRECT_URL" -c "SELECT version();" > /dev/null 2>&1; then
        echo -e "${GREEN}✅ Direct connection successful${NC}"
        psql "$DIRECT_URL" -c "SELECT current_database(), current_user, NOW();"
    else
        echo -e "${RED}❌ Direct connection failed${NC}"
    fi
else
    echo -e "${YELLOW}⚠️ psql not available - install with: apt-get install postgresql-client${NC}"
fi
echo ""

# Test 6: Docker Network Test
echo -e "${BLUE}🐳 Docker Network Simulation${NC}"

if command -v docker &> /dev/null; then
    echo "Testing from within Docker container..."
    
    # Create a test container and run connectivity tests
    docker run --rm -it \
        --dns=8.8.8.8 \
        --dns=1.1.1.1 \
        alpine:latest sh -c "
        apk add --no-cache postgresql-client curl bind-tools;
        echo 'Testing DNS from container...';
        nslookup $SUPABASE_HOST;
        echo 'Testing ping from container...';
        ping -c 2 $SUPABASE_HOST;
        echo 'Testing PostgreSQL connection from container...';
        psql 'postgresql://postgres.${SUPABASE_PROJECT}:b6Sfj*D!Gr98vPY@${SUPABASE_HOST}:${SUPABASE_POOLER_PORT}/postgres' -c 'SELECT 1;'
    " 2>/dev/null || echo -e "${RED}❌ Docker test failed${NC}"
else
    echo -e "${YELLOW}⚠️ Docker not available${NC}"
fi
echo ""

# Test 7: Network Configuration
echo -e "${BLUE}🔧 Network Configuration${NC}"
echo "Active network interfaces:"
ip addr show | grep -E "inet |UP," | head -10

echo ""
echo "Routing table:"
ip route | head -5

echo ""
echo "Firewall status:"
if command -v ufw &> /dev/null; then
    ufw status
elif command -v iptables &> /dev/null; then
    iptables -L -n | head -10
else
    echo "No firewall tools found"
fi
echo ""

# Test 8: SSL/TLS Test
echo -e "${BLUE}🔒 SSL/TLS Test${NC}"
if command -v openssl &> /dev/null; then
    echo "Testing SSL connection to pooler port..."
    timeout 10 openssl s_client -connect $SUPABASE_HOST:$SUPABASE_POOLER_PORT -servername $SUPABASE_HOST </dev/null 2>/dev/null | grep -E "Verify return code|subject|issuer" || echo "SSL test failed"
    
    echo "Testing SSL connection to direct port..."
    timeout 10 openssl s_client -connect $SUPABASE_HOST:$SUPABASE_DIRECT_PORT -servername $SUPABASE_HOST </dev/null 2>/dev/null | grep -E "Verify return code|subject|issuer" || echo "SSL test failed"
else
    echo -e "${YELLOW}⚠️ OpenSSL not available${NC}"
fi
echo ""

# Test 9: Python asyncpg Test
echo -e "${BLUE}🐍 Python AsyncPG Test${NC}"
if command -v python3 &> /dev/null; then
    echo "Creating Python test script..."
    cat > /tmp/test_asyncpg.py << 'EOF'
import asyncio
import asyncpg
import sys
import time

async def test_connection():
    connections = [
        ("Pooler", "postgresql://postgres.emzlxdutmhmbvaetphpu:b6Sfj*D!Gr98vPY@aws-0-us-east-1.pooler.supabase.com:6543/postgres"),
        ("Direct", "postgresql://postgres.emzlxdutmhmbvaetphpu:b6Sfj*D!Gr98vPY@aws-0-us-east-1.pooler.supabase.com:5432/postgres")
    ]
    
    for name, url in connections:
        try:
            print(f"Testing {name} connection...")
            start_time = time.time()
            conn = await asyncio.wait_for(asyncpg.connect(url), timeout=15.0)
            connect_time = time.time() - start_time
            
            version = await conn.fetchval('SELECT version()')
            await conn.close()
            
            print(f"✅ {name}: Success ({connect_time:.3f}s)")
            print(f"   Version: {version.split()[1]}")
        except Exception as e:
            print(f"❌ {name}: Failed - {e}")

if __name__ == "__main__":
    asyncio.run(test_connection())
EOF

    # Check if asyncpg is available
    if python3 -c "import asyncpg" 2>/dev/null; then
        python3 /tmp/test_asyncpg.py
    else
        echo -e "${YELLOW}⚠️ asyncpg not available - install with: pip3 install asyncpg${NC}"
        echo "Installing asyncpg and testing..."
        if pip3 install asyncpg 2>/dev/null; then
            python3 /tmp/test_asyncpg.py
        else
            echo -e "${RED}❌ Failed to install asyncpg${NC}"
        fi
    fi
    
    rm -f /tmp/test_asyncpg.py
else
    echo -e "${YELLOW}⚠️ Python3 not available${NC}"
fi
echo ""

# Summary
echo -e "${BLUE}📊 Test Summary${NC}"
echo "=================================="
echo "This test has checked:"
echo "✓ DNS resolution (system and multiple servers)"
echo "✓ Network connectivity (ping, port tests)"
echo "✓ PostgreSQL connections (pooler and direct)"
echo "✓ Docker network simulation"
echo "✓ SSL/TLS connectivity"
echo "✓ Python asyncpg compatibility"
echo ""
echo "If any tests failed, check:"
echo "1. Firewall rules (ufw/iptables)"
echo "2. DNS configuration (/etc/resolv.conf)"
echo "3. Network route to Supabase (traceroute)"
echo "4. Supabase project status and credentials"
echo ""
echo -e "${GREEN}Test completed at $(date)${NC}"