#!/bin/bash

# CoSim Docker Management Script
# Convenient commands for managing the Docker environment

set -e

PROJECT_NAME="cosim"
COMPOSE_FILE="docker-compose.yml"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color
REDIS_CLI_CMD="redis-cli"

print_header() {
    echo -e "${GREEN}=====================================${NC}"
    echo -e "${GREEN}  CoSim Docker Manager${NC}"
    echo -e "${GREEN}=====================================${NC}"
    echo ""
}

print_success() {
    echo -e "${GREEN}✓${NC} $1"
}

print_error() {
    echo -e "${RED}✗${NC} $1"
}

print_info() {
    echo -e "${YELLOW}ℹ${NC} $1"
}

case "$1" in
    start)
        print_header
        print_info "Starting all CoSim services..."
        docker-compose up -d
        print_success "Services started!"
        echo ""
        print_info "Access points:"
        echo "  • Web IDE: http://localhost:5173"
        echo "  • API Gateway: http://localhost:8080"
        echo "  • Redis Commander: http://localhost:8081"
        echo "  • API Docs: http://localhost:8080/docs"
        echo "  • Yjs Health: http://localhost:1234/health"
        ;;
    
    stop)
        print_header
        print_info "Stopping all services..."
        docker-compose down
        print_success "Services stopped!"
        ;;
    
    restart)
        print_header
        print_info "Restarting all services..."
        docker-compose down
        docker-compose up -d
        print_success "Services restarted!"
        ;;
    
    logs)
        if [ -z "$2" ]; then
            docker-compose logs -f
        else
            docker-compose logs -f "$2"
        fi
        ;;
    
    status)
        print_header
        docker-compose ps
        ;;
    
    health)
        print_header
        print_info "Checking service health..."
        echo ""
        
        # Check web
        if curl -s http://localhost:5173 > /dev/null; then
            print_success "Web IDE (http://localhost:5173)"
        else
            print_error "Web IDE not responding"
        fi
        
        # Check API Gateway
        if curl -s http://localhost:8080/docs > /dev/null; then
            print_success "API Gateway (http://localhost:8080)"
        else
            print_error "API Gateway not responding"
        fi
        
        # Check Yjs
        if curl -s http://localhost:1234/health > /dev/null; then
            print_success "Yjs Collaboration Server (http://localhost:1234)"
        else
            print_error "Yjs Server not responding"
        fi
        
        # Check Postgres
        if docker-compose exec -T postgres pg_isready -U cosim > /dev/null 2>&1; then
            print_success "PostgreSQL"
        else
            print_error "PostgreSQL not ready"
        fi
        
        # Check Redis
        if docker-compose exec -T redis ${REDIS_CLI_CMD} ping > /dev/null 2>&1; then
            print_success "Redis"
        else
            print_error "Redis not responding"
        fi
        ;;
    
    rebuild)
        print_header
        if [ -z "$2" ]; then
            print_info "Rebuilding all services..."
            docker-compose build --no-cache
            docker-compose up -d
        else
            print_info "Rebuilding $2..."
            docker-compose build --no-cache "$2"
            docker-compose up -d "$2"
        fi
        print_success "Rebuild complete!"
        ;;
    
    clean)
        print_header
        print_info "Cleaning up Docker resources..."
        read -p "This will remove all stopped containers, unused networks, and dangling images. Continue? (y/N) " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            docker-compose down
            docker system prune -f
            print_success "Cleanup complete!"
        else
            print_info "Cleanup cancelled"
        fi
        ;;
    
    reset)
        print_header
        print_error "WARNING: This will delete all data including the database!"
        read -p "Are you sure? Type 'yes' to confirm: " -r
        echo
        if [[ $REPLY == "yes" ]]; then
            print_info "Resetting environment..."
            docker-compose down -v
            docker-compose up -d
            print_success "Environment reset complete!"
        else
            print_info "Reset cancelled"
        fi
        ;;
    
    shell)
        if [ -z "$2" ]; then
            print_error "Please specify a service: web, api-gateway, postgres, etc."
            exit 1
        fi
        print_info "Opening shell in $2..."
        docker-compose exec "$2" sh
        ;;
    
    install)
        if [ "$2" = "frontend" ]; then
            print_info "Installing frontend dependencies inside container..."
            docker-compose exec web npm install
            print_success "Dependencies installed!"
        elif [ "$2" = "backend" ]; then
            print_info "Rebuilding backend services..."
            docker-compose build auth-agent project-agent session-orchestrator collab-agent api-gateway
            docker-compose up -d
            print_success "Backend rebuilt!"
        else
            print_error "Please specify: frontend or backend"
        fi
        ;;
    
    db)
        case "$2" in
            connect)
                print_info "Connecting to PostgreSQL..."
                docker-compose exec postgres psql -U cosim -d cosim
                ;;
            backup)
                BACKUP_FILE="backup_$(date +%Y%m%d_%H%M%S).sql"
                print_info "Backing up database to $BACKUP_FILE..."
                docker-compose exec -T postgres pg_dump -U cosim cosim > "$BACKUP_FILE"
                print_success "Database backed up to $BACKUP_FILE"
                ;;
            restore)
                if [ -z "$3" ]; then
                    print_error "Please specify backup file"
                    exit 1
                fi
                print_info "Restoring database from $3..."
                cat "$3" | docker-compose exec -T postgres psql -U cosim -d cosim
                print_success "Database restored!"
                ;;
            *)
                print_error "Usage: $0 db {connect|backup|restore <file>}"
                exit 1
                ;;
        esac
        ;;

    redis)
        case "$2" in
            cli)
                print_info "Opening redis-cli shell..."
                docker-compose exec redis ${REDIS_CLI_CMD}
                ;;
            flush)
                read -p "This will FLUSHALL the Redis cache. Continue? (y/N) " -n 1 -r
                echo
                if [[ $REPLY =~ ^[Yy]$ ]]; then
                    docker-compose exec redis ${REDIS_CLI_CMD} FLUSHALL
                    print_success "Redis cache cleared"
                else
                    print_info "Flush cancelled"
                fi
                ;;
            stats)
                print_info "Redis INFO (memory)"
                docker-compose exec redis ${REDIS_CLI_CMD} INFO memory
                ;;
            *)
                print_error "Usage: $0 redis {cli|flush|stats}"
                exit 1
                ;;
        esac
        ;;

    *)
        print_header
        echo "Usage: $0 {command} [options]"
        echo ""
        echo "Commands:"
        echo "  start              Start all services"
        echo "  stop               Stop all services"
        echo "  restart            Restart all services"
        echo "  logs [service]     View logs (optionally for specific service)"
        echo "  status             Show service status"
        echo "  health             Check health of all services"
        echo "  rebuild [service]  Rebuild service(s) from scratch"
        echo "  clean              Clean up Docker resources"
        echo "  reset              Reset environment (deletes all data!)"
        echo "  shell <service>    Open shell in service container"
        echo "  install {frontend|backend}  Install dependencies"
        echo "  db {connect|backup|restore <file>}  Database operations"
        echo "  redis {cli|flush|stats}     Redis utilities"
        echo ""
        echo "Examples:"
        echo "  $0 start                    # Start all services"
        echo "  $0 logs web                 # View web logs"
        echo "  $0 rebuild web              # Rebuild just the web service"
        echo "  $0 shell web                # Open shell in web container"
        echo "  $0 db backup                # Backup database"
        echo "  $0 health                   # Check all services"
        exit 1
        ;;
esac
