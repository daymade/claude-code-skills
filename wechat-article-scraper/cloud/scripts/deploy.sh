#!/bin/bash
# One-click cloud deployment script for WeChat Article Scraper

set -e

echo "🚀 WeChat Article Scraper - Cloud Deployment"
echo "=============================================="

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check dependencies
check_dependency() {
  if ! command -v $1 &> /dev/null; then
    echo -e "${RED}❌ $1 is not installed${NC}"
    return 1
  fi
  echo -e "${GREEN}✅ $1 installed${NC}"
  return 0
}

echo ""
echo "📋 Checking dependencies..."
check_dependency node || { echo "Please install Node.js: https://nodejs.org/"; exit 1; }
check_dependency npm || { echo "Please install npm"; exit 1; }
check_dependency vercel || { echo "Installing Vercel CLI..."; npm i -g vercel; }
check_dependency supabase || { echo "Installing Supabase CLI..."; npm i -g supabase; }

# Setup
echo ""
echo "⚙️  Setup..."
cd "$(dirname "$0")/.."

if [ ! -f .env.local ]; then
  echo -e "${YELLOW}⚠️  .env.local not found. Creating from template...${NC}"
  cat > .env.local << 'EOF'
# Supabase Configuration
# Get these from your Supabase project settings
NEXT_PUBLIC_SUPABASE_URL=https://your-project.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=your-anon-key
SUPABASE_SERVICE_ROLE_KEY=your-service-role-key

# Optional: OpenAI for AI features
OPENAI_API_KEY=your-openai-key
EOF
  echo -e "${YELLOW}⚠️  Please edit .env.local with your actual credentials${NC}"
fi

# Install dependencies
echo ""
echo "📦 Installing dependencies..."
npm install

# Setup Supabase (if not already linked)
echo ""
echo "🗄️  Setting up Supabase..."
if [ ! -d supabase/.temp ]; then
  echo "Initializing Supabase..."
  supabase login
  echo "Please create a project at https://app.supabase.com and link it:"
  echo "supabase link --project-ref your-project-ref"
fi

# Deploy database migrations
echo ""
echo "🔄 Deploying database migrations..."
supabase db push

# Generate types
echo ""
echo "📝 Generating TypeScript types..."
if [ -n "$SUPABASE_PROJECT_ID" ]; then
  supabase gen types typescript --project-id "$SUPABASE_PROJECT_ID" > src/types/supabase.ts
fi

# Build
echo ""
echo "🔨 Building application..."
npm run build

# Deploy to Vercel
echo ""
echo "🚀 Deploying to Vercel..."
vercel --prod

echo ""
echo -e "${GREEN}✅ Deployment complete!${NC}"
echo ""
echo "Next steps:"
echo "1. Configure environment variables in Vercel dashboard"
echo "2. Set up custom domain (optional)"
echo "3. Share the deployed URL with your team"
echo ""
