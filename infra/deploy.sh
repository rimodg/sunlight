#!/usr/bin/env bash
set -euo pipefail

# SUNLIGHT Deploy Script
# Usage:
#   ./deploy.sh demo     — Deploy demo environment
#   ./deploy.sh staging  — Deploy staging
#   ./deploy.sh prod     — Deploy production
#   ./deploy.sh local    — Run locally via docker-compose

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
ENV="${1:-local}"

echo "☀️  SUNLIGHT Deploy — Environment: $ENV"
echo "============================================"

case "$ENV" in
  local)
    echo "Starting local stack via docker-compose..."
    cd "$ROOT_DIR"
    docker compose up --build -d
    echo ""
    echo "Waiting for services..."
    sleep 5
    echo ""
    echo "Running health check..."
    curl -sf http://localhost:8000/health | python3 -m json.tool
    echo ""
    echo "✅ SUNLIGHT running at http://localhost:8000"
    echo "   Dashboard: http://localhost:8000/dashboard"
    echo "   API Docs:  http://localhost:8000/docs"
    echo "   DB Admin:  localhost:5432 (sunlight/changeme)"
    ;;

  demo|staging|prod)
    cd "$SCRIPT_DIR/aws"

    # Check prerequisites
    command -v terraform >/dev/null 2>&1 || { echo "❌ terraform not found"; exit 1; }
    command -v aws >/dev/null 2>&1 || { echo "❌ aws CLI not found"; exit 1; }
    command -v docker >/dev/null 2>&1 || { echo "❌ docker not found"; exit 1; }

    # Verify AWS credentials
    aws sts get-caller-identity > /dev/null 2>&1 || { echo "❌ AWS not authenticated"; exit 1; }

    ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
    REGION=$(grep aws_region "${ENV}.tfvars" | cut -d'"' -f2 || echo "us-east-1")
    ECR_REPO="${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com/sunlight"

    echo "AWS Account: $ACCOUNT_ID"
    echo "Region: $REGION"
    echo ""

    # Build and push Docker image
    echo "📦 Building Docker image..."
    cd "$ROOT_DIR"
    docker build -t sunlight:latest .

    echo "📤 Pushing to ECR..."
    aws ecr get-login-password --region "$REGION" | docker login --username AWS --password-stdin "$ECR_REPO" 2>/dev/null || true
    aws ecr create-repository --repository-name sunlight --region "$REGION" 2>/dev/null || true
    docker tag sunlight:latest "${ECR_REPO}:latest"
    docker push "${ECR_REPO}:latest"

    # Terraform apply
    echo "🏗️  Running Terraform..."
    cd "$SCRIPT_DIR/aws"

    terraform init -upgrade
    terraform plan -var-file="${ENV}.tfvars" \
      -var="db_password=$(aws ssm get-parameter --name /sunlight-${ENV}/db-password --with-decryption --query Parameter.Value --output text 2>/dev/null || echo 'changeme-$(openssl rand -hex 8)')" \
      -var="container_image=${ECR_REPO}:latest" \
      -out=tfplan

    echo ""
    read -p "Apply this plan? (y/N) " confirm
    if [[ "$confirm" == "y" || "$confirm" == "Y" ]]; then
      terraform apply tfplan
      echo ""
      echo "✅ Deployed!"
      terraform output -json | python3 -c "
import json, sys
o = json.load(sys.stdin)
print(f'API URL: {o[\"api_url\"][\"value\"]}')
print(f'RDS:     {o[\"rds_endpoint\"][\"value\"]}')
"
    fi
    ;;

  *)
    echo "Usage: $0 {local|demo|staging|prod}"
    exit 1
    ;;
esac
