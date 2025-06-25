#!/bin/bash
# Quick Push to GitHub Script
# =========================

set -e

echo "🚀 DRL Trading Bot Collection - GitHub Push Script"
echo "=================================================="

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Get current directory
CURRENT_DIR=$(pwd)
echo -e "${GREEN}Current directory: $CURRENT_DIR${NC}"

# Check if we're in the right directory
if [[ ! -f "README.md" ]] || [[ ! -d "consolidado" ]]; then
    echo -e "${RED}❌ Error: Not in the correct repository directory${NC}"
    echo "Please run this script from the drl_repos directory"
    exit 1
fi

# Check git status
echo -e "${YELLOW}📋 Checking git status...${NC}"
git status

# Prompt for GitHub username
echo ""
read -p "🔗 Enter your GitHub username: " GITHUB_USERNAME

if [[ -z "$GITHUB_USERNAME" ]]; then
    echo -e "${RED}❌ GitHub username cannot be empty${NC}"
    exit 1
fi

# Prompt for repository name (with default)
echo ""
read -p "📦 Enter repository name (default: drift-trading-bot-collection): " REPO_NAME
REPO_NAME=${REPO_NAME:-drift-trading-bot-collection}

# Construct GitHub URL
GITHUB_URL="https://github.com/${GITHUB_USERNAME}/${REPO_NAME}.git"
echo -e "${YELLOW}🔗 GitHub URL: $GITHUB_URL${NC}"

# Check if remote already exists
if git remote get-url origin &> /dev/null; then
    echo -e "${YELLOW}⚠️  Remote 'origin' already exists${NC}"
    EXISTING_URL=$(git remote get-url origin)
    echo "Existing URL: $EXISTING_URL"
    
    read -p "Do you want to update the remote URL? (y/N): " UPDATE_REMOTE
    if [[ $UPDATE_REMOTE =~ ^[Yy]$ ]]; then
        git remote set-url origin $GITHUB_URL
        echo -e "${GREEN}✅ Remote URL updated${NC}"
    fi
else
    # Add the remote
    echo -e "${YELLOW}🔗 Adding GitHub remote...${NC}"
    git remote add origin $GITHUB_URL
    echo -e "${GREEN}✅ Remote added successfully${NC}"
fi

# Verify remote
echo -e "${YELLOW}📋 Verifying remote...${NC}"
git remote -v

# Push to GitHub
echo ""
echo -e "${YELLOW}🚀 Pushing to GitHub...${NC}"
echo "This will push the following commits:"
git log --oneline -n 5

echo ""
read -p "Proceed with push? (Y/n): " PROCEED
if [[ ! $PROCEED =~ ^[Nn]$ ]]; then
    git push -u origin main
    echo -e "${GREEN}✅ Successfully pushed to GitHub!${NC}"
    
    echo ""
    echo -e "${GREEN}🎉 Repository is now available at:${NC}"
    echo -e "${GREEN}🔗 https://github.com/${GITHUB_USERNAME}/${REPO_NAME}${NC}"
    
    echo ""
    echo -e "${YELLOW}📋 Next steps:${NC}"
    echo "1. Visit your repository on GitHub"
    echo "2. Add a description and topics"
    echo "3. Enable Issues and Projects"
    echo "4. Set up branch protection (optional)"
    echo "5. Invite collaborators (optional)"
    
    echo ""
    echo -e "${GREEN}🎯 Repository contents:${NC}"
    echo "📄 README.md - Main documentation"
    echo "🎯 consolidado/ - Main trading system for Drift.trade"
    echo "📚 repos-downloads/ - Reference repositories"
    echo "📋 SETUP_GITHUB.md - GitHub setup guide"
    
else
    echo -e "${YELLOW}⏸️  Push cancelled by user${NC}"
fi

echo ""
echo -e "${GREEN}🚀 DRL Trading Bot Collection setup complete!${NC}"