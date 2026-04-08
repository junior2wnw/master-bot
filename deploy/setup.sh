#!/usr/bin/env bash
# ============================================================================
# ПриДел — Turnkey Deployment Script for Ubuntu 20.04 / 22.04 / 24.04
# ============================================================================
#
# Что делает:
#   1. Проверяет ОС и зависимости
#   2. Устанавливает Docker CE + Docker Compose v2 (если нет)
#   3. Генерирует .env с криптографически стойкими секретами
#   4. Собирает и запускает контейнеры
#   5. Ждёт готовности БД
#   6. Запускает Alembic миграции
#   7. Загружает seed-данные
#   8. Настраивает systemd для автозапуска
#   9. Настраивает UFW firewall
#  10. Показывает статус и URL-ы
#
# Использование:
#   sudo bash deploy/setup.sh
#   sudo bash deploy/setup.sh --max-bot-token YOUR_TOKEN
#   sudo bash deploy/setup.sh --skip-firewall --skip-systemd
#
# ============================================================================

set -euo pipefail

# === Colors ===
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

log()    { echo -e "${GREEN}[✓]${NC} $1"; }
warn()   { echo -e "${YELLOW}[!]${NC} $1"; }
err()    { echo -e "${RED}[✗]${NC} $1" >&2; }
header() { echo -e "\n${CYAN}${BOLD}=== $1 ===${NC}\n"; }

# === Parse arguments ===
MAX_BOT_TOKEN=""
WEBAPP_URL=""
SKIP_FIREWALL=false
SKIP_SYSTEMD=false
SKIP_SEED=false
DOMAIN=""
APP_PORT=8000

while [[ $# -gt 0 ]]; do
    case $1 in
        --max-bot-token|--bot-token) MAX_BOT_TOKEN="$2"; shift 2 ;;
        --webapp-url)   WEBAPP_URL="$2"; shift 2 ;;
        --domain)        DOMAIN="$2"; shift 2 ;;
        --port)          APP_PORT="$2"; shift 2 ;;
        --skip-firewall) SKIP_FIREWALL=true; shift ;;
        --skip-systemd)  SKIP_SYSTEMD=true; shift ;;
        --skip-seed)     SKIP_SEED=true; shift ;;
        --help|-h)
            echo "Usage: sudo bash deploy/setup.sh [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --max-bot-token TOKEN   MAX Bot Token (or set later in .env)"
            echo "  --webapp-url URL        Public HTTPS URL for Mini App"
            echo "  --domain DOMAIN     Domain name for nginx (optional)"
            echo "  --port PORT         App port (default: 8000)"
            echo "  --skip-firewall     Don't configure UFW"
            echo "  --skip-systemd      Don't create systemd service"
            echo "  --skip-seed         Don't run seed script"
            exit 0
            ;;
        *) err "Unknown option: $1"; exit 1 ;;
    esac
done

# === Preflight checks ===
header "Preflight Checks"

if [[ $EUID -ne 0 ]]; then
    err "Этот скрипт нужно запускать от root: sudo bash deploy/setup.sh"
    exit 1
fi

# Detect project directory (script is in deploy/)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

if [[ ! -f "$PROJECT_DIR/docker-compose.yml" ]]; then
    err "docker-compose.yml не найден в $PROJECT_DIR"
    err "Запускайте скрипт из корня проекта: sudo bash deploy/setup.sh"
    exit 1
fi

cd "$PROJECT_DIR"
log "Рабочая директория: $PROJECT_DIR"

# Check Ubuntu version
if [[ -f /etc/os-release ]]; then
    . /etc/os-release
    log "ОС: $PRETTY_NAME"
    if [[ "$ID" != "ubuntu" && "$ID" != "debian" ]]; then
        warn "Скрипт оптимизирован для Ubuntu, но попробуем продолжить"
    fi
else
    warn "Не удалось определить ОС"
fi

# === Install Docker ===
header "Docker"

install_compose_v2() {
    if docker compose version &>/dev/null; then
        return 0
    fi

    if apt-get install -y -qq docker-compose-plugin; then
        :
    else
        warn "Пакет docker-compose-plugin недоступен, пробуем docker-compose-v2"
        apt-get install -y -qq docker-compose-v2
    fi
}

if command -v docker &>/dev/null; then
    DOCKER_VERSION=$(docker --version | grep -oP '\d+\.\d+\.\d+' | head -1)
    log "Docker уже установлен: $DOCKER_VERSION"
else
    log "Устанавливаем Docker CE..."
    apt-get update -qq
    apt-get install -y -qq ca-certificates curl gnupg lsb-release

    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | \
        gpg --dearmor -o /etc/apt/keyrings/docker.gpg 2>/dev/null
    chmod a+r /etc/apt/keyrings/docker.gpg

    CODENAME=$(. /etc/os-release && echo "$VERSION_CODENAME" 2>/dev/null || echo "jammy")
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
        https://download.docker.com/linux/ubuntu $CODENAME stable" | \
        tee /etc/apt/sources.list.d/docker.list > /dev/null

    apt-get update -qq
    apt-get install -y -qq docker-ce docker-ce-cli containerd.io

    systemctl enable --now docker
    log "Docker установлен: $(docker --version)"
fi

install_compose_v2

# Verify docker compose v2
if docker compose version &>/dev/null; then
    log "Docker Compose: $(docker compose version --short)"
else
    err "Docker Compose v2 не найден. Установите docker-compose-plugin или docker-compose-v2"
    exit 1
fi

# === Generate .env ===
header "Конфигурация (.env)"

generate_secret() {
    openssl rand -base64 32 | tr -d '/+=' | head -c "$1"
}

DB_PASSWORD=$(generate_secret 24)
REDIS_PASSWORD=$(generate_secret 24)
APP_SECRET=$(generate_secret 48)

if [[ -f .env ]]; then
    warn ".env уже существует — создаём бэкап .env.bak"
    cp .env .env.bak
fi

cat > .env <<ENVEOF
# ============================================================================
# ПриДел — Environment Configuration
# Generated: $(date -u +"%Y-%m-%dT%H:%M:%SZ")
# ============================================================================

# MAX Bot
MAX_BOT_TOKEN=${MAX_BOT_TOKEN}
MAX_API_BASE_URL=https://platform-api.max.ru
MAX_POLLING_TIMEOUT_SEC=30
WEBAPP_URL=${WEBAPP_URL}

# Database
DATABASE_URL=postgresql+asyncpg://masterbot:${DB_PASSWORD}@db:5432/masterbot
DATABASE_URL_SYNC=postgresql://masterbot:${DB_PASSWORD}@db:5432/masterbot
POSTGRES_USER=masterbot
POSTGRES_PASSWORD=${DB_PASSWORD}
POSTGRES_DB=masterbot

# Redis
REDIS_URL=redis://:${REDIS_PASSWORD}@redis:6379/0
REDIS_PASSWORD=${REDIS_PASSWORD}

# Application
APP_ENV=production
APP_DEBUG=false
APP_SECRET_KEY=${APP_SECRET}
APP_HOST=0.0.0.0
APP_PORT=${APP_PORT}

# Platform
PLATFORM_NAME=ПриДел
PLATFORM_FEE_PCT=20.0
SENIOR_MASTER_SHARE_PCT=5.0
ADMIN_SHARE_PCT=5.0
DEFAULT_CURRENCY=RUB
DEFAULT_CITY=Стерлитамак
DEFAULT_REGION=Башкортостан

# AI (disabled by default)
AI_PROVIDER=disabled
AI_API_KEY=
AI_API_URL=
AI_MODEL=

# Payment
PAYMENT_PHONE=
PAYMENT_BANK_NAME=
PAYMENT_RECIPIENT_NAME=

# Logging
LOG_LEVEL=INFO
LOG_FORMAT=json

# Admin (set external messenger IDs)
OWNER_TELEGRAM_ID=0
ADMIN_TELEGRAM_IDS=
ENVEOF

chmod 600 .env
log ".env сгенерирован (пароли: криптостойкие, права: 600)"

if [[ -z "$MAX_BOT_TOKEN" ]]; then
    warn "MAX_BOT_TOKEN не задан. Укажите его в .env перед запуском бота."
    warn "Получите токен в кабинете партнёров MAX: business.max.ru"
fi

if [[ -z "$WEBAPP_URL" ]]; then
    warn "WEBAPP_URL не задан. Mini App в MAX не откроется, пока не укажете публичный HTTPS URL."
fi

# === Update docker-compose for production (password-protected Redis) ===
header "Docker Compose (production overlay)"

cat > docker-compose.override.yml <<DCEOF
# Production overrides — auto-generated by setup.sh
services:
  db:
    environment:
      POSTGRES_USER: \${POSTGRES_USER}
      POSTGRES_PASSWORD: \${POSTGRES_PASSWORD}
      POSTGRES_DB: \${POSTGRES_DB}
    volumes:
      - pgdata:/var/lib/postgresql/data
    restart: unless-stopped

  redis:
    command: redis-server --requirepass \${REDIS_PASSWORD} --maxmemory 128mb --maxmemory-policy allkeys-lru
    restart: unless-stopped

  app:
    restart: unless-stopped
    logging:
      driver: json-file
      options:
        max-size: "50m"
        max-file: "5"
    deploy:
      resources:
        limits:
          memory: 512M
DCEOF

log "docker-compose.override.yml создан"

# === Build and start ===
header "Сборка и запуск контейнеров"

log "Собираем образ приложения..."
docker compose build --quiet app

log "Запускаем контейнеры..."
docker compose up -d

# === Wait for DB ===
header "Ожидание готовности PostgreSQL"

MAX_RETRIES=30
RETRY=0
until docker compose exec -T db pg_isready -U masterbot -q 2>/dev/null; do
    RETRY=$((RETRY + 1))
    if [[ $RETRY -ge $MAX_RETRIES ]]; then
        err "PostgreSQL не готов после ${MAX_RETRIES} попыток"
        docker compose logs db
        exit 1
    fi
    echo -n "."
    sleep 1
done
echo ""
log "PostgreSQL готов"

# Wait for Redis
RETRY=0
until docker compose exec -T redis redis-cli -a "${REDIS_PASSWORD}" ping 2>/dev/null | grep -q PONG; do
    RETRY=$((RETRY + 1))
    if [[ $RETRY -ge $MAX_RETRIES ]]; then
        err "Redis не готов после ${MAX_RETRIES} попыток"
        exit 1
    fi
    sleep 1
done
log "Redis готов"

# === Run migrations ===
header "Миграции базы данных"

log "Запускаем Alembic миграции..."
docker compose exec -T app python -m alembic upgrade head
log "Миграции применены"

# === Seed data ===
if [[ "$SKIP_SEED" == "false" ]]; then
    header "Загрузка начальных данных"
    log "Запускаем seed..."
    docker compose exec -T app python -m scripts.seed
    log "Seed-данные загружены"
fi

# === Health check ===
header "Проверка здоровья"

sleep 2
RETRY=0
until curl -sf "http://localhost:${APP_PORT}/health" >/dev/null 2>&1; do
    RETRY=$((RETRY + 1))
    if [[ $RETRY -ge 15 ]]; then
        warn "Health-check не прошёл, но контейнеры запущены"
        break
    fi
    sleep 1
done

if curl -sf "http://localhost:${APP_PORT}/health" 2>/dev/null | grep -q '"ok"'; then
    log "Health-check: OK"
fi

# === Systemd service ===
if [[ "$SKIP_SYSTEMD" == "false" ]]; then
    header "Systemd (автозапуск)"

    cat > /etc/systemd/system/masterbot.service <<SVCEOF
[Unit]
Description=ПриДел - Service Master Platform
After=docker.service
Requires=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=${PROJECT_DIR}
ExecStart=/usr/bin/docker compose up -d
ExecStop=/usr/bin/docker compose down
ExecReload=/usr/bin/docker compose up -d --build --force-recreate app
TimeoutStartSec=120

[Install]
WantedBy=multi-user.target
SVCEOF

    systemctl daemon-reload
    systemctl enable masterbot.service
    log "Systemd сервис создан и включён (masterbot.service)"
fi

# === Firewall ===
if [[ "$SKIP_FIREWALL" == "false" ]] && command -v ufw &>/dev/null; then
    header "Firewall (UFW)"

    ufw --force enable 2>/dev/null || true
    ufw allow ssh
    ufw allow 80/tcp
    ufw allow 443/tcp
    # App port only from localhost (за nginx)
    ufw allow from 127.0.0.1 to any port "$APP_PORT"
    log "UFW настроен: SSH + HTTP + HTTPS"
fi

# === Log rotation ===
header "Ротация логов"

cat > /etc/logrotate.d/masterbot <<LOGEOF
${PROJECT_DIR}/logs/*.log {
    daily
    missingok
    rotate 14
    compress
    delaycompress
    notifempty
    copytruncate
}
LOGEOF
mkdir -p "${PROJECT_DIR}/logs"
log "Ротация логов настроена (14 дней)"

# === Summary ===
header "ГОТОВО!"

echo -e "${BOLD}ПриДел успешно развёрнут!${NC}"
echo ""
echo -e "  API:        http://localhost:${APP_PORT}"
echo -e "  Health:     http://localhost:${APP_PORT}/health"
echo -e "  Ready:      http://localhost:${APP_PORT}/ready"
echo -e "  Docs:       http://localhost:${APP_PORT}/docs (только в dev)"
echo ""
echo -e "  Проект:     ${PROJECT_DIR}"
echo -e "  .env:       ${PROJECT_DIR}/.env"
echo ""
echo -e "${BOLD}Управление:${NC}"
echo -e "  docker compose logs -f app    # Логи приложения"
echo -e "  docker compose restart app    # Только перезапуск процесса без пересборки"
echo -e "  docker compose up -d --build app  # Подтянуть новый код backend + Mini App shell"
echo -e "  docker compose up -d --force-recreate app  # Подхватить изменённый .env без изменения кода"
echo -e "  docker compose up -d --build --force-recreate app  # Обновить и код, и env одновременно"
echo -e "  docker compose exec app python -m alembic upgrade head  # Миграции"
echo -e "  docker compose exec app python -m scripts.seed          # Seed"
echo -e "  systemctl restart masterbot   # Рестарт через systemd"
echo ""

if [[ -z "$MAX_BOT_TOKEN" ]]; then
    echo -e "${YELLOW}${BOLD}⚠ Не забудьте:${NC}"
    echo -e "  1. Укажите MAX_BOT_TOKEN в .env"
    echo -e "  2. Укажите OWNER_TELEGRAM_ID в .env"
    echo -e "  3. Примените .env: docker compose up -d --force-recreate app"
    echo ""
fi

echo -e "${GREEN}${BOLD}Готово. Развёртывание завершено за $(( SECONDS / 60 ))м $(( SECONDS % 60 ))с${NC}"
