#!/bin/bash

# Script to create clean 18.0 branch with only ready modules
# Uses 3-step approach: migration -> ready-modules -> 18.0

set -e  # Exit on any error

# Define the modules that are confirmed working in Odoo 18.0
READY_MODULES=(
    "llm"
    "llm_thread"
    "llm_tool"
    "llm_assistant"
    "llm_openai"
    "llm_mistral"
    "llm_ollama"
    "llm_letta"
    "llm_mcp_server"
    "llm_generate"
    "web_json_editor"
)

SOURCE_BRANCH="18.0-migration"
INTERMEDIATE_BRANCH="18.0-ready-modules"
TARGET_BRANCH="18.0"

echo "🚀 Creating clean $TARGET_BRANCH branch with only ready modules"
echo "📋 Ready modules: ${READY_MODULES[*]}"
echo ""
echo "🔄 Workflow:"
echo "  1. $SOURCE_BRANCH → $INTERMEDIATE_BRANCH (remove non-ready modules)"
echo "  2. $INTERMEDIATE_BRANCH → $TARGET_BRANCH (create production branch)"
echo ""

# Verify we're in a git repository
if ! git rev-parse --git-dir > /dev/null 2>&1; then
    echo "❌ Error: Not in a git repository"
    exit 1
fi

# Verify source branch exists
if ! git rev-parse --verify "$SOURCE_BRANCH" > /dev/null 2>&1; then
    echo "❌ Error: Source branch '$SOURCE_BRANCH' does not exist"
    exit 1
fi

# Check for uncommitted changes
if ! git diff --quiet; then
    echo "⚠️  Warning: You have uncommitted changes. Please commit or stash them first."
    echo "Uncommitted files:"
    git diff --name-only
    exit 1
fi

# Store current branch to return to it later
CURRENT_BRANCH=$(git branch --show-current)
echo "📍 Current branch: $CURRENT_BRANCH"

# Step 1: Create intermediate branch from migration
echo ""
echo "📝 Step 1: Creating $INTERMEDIATE_BRANCH from $SOURCE_BRANCH..."

if git rev-parse --verify "$INTERMEDIATE_BRANCH" > /dev/null 2>&1; then
    echo "⚠️  $INTERMEDIATE_BRANCH already exists. Deleting and recreating..."
    git branch -D "$INTERMEDIATE_BRANCH"
fi

git checkout "$SOURCE_BRANCH"
git checkout -b "$INTERMEDIATE_BRANCH"
echo "✅ Created $INTERMEDIATE_BRANCH"

# Step 2: Remove non-ready modules
echo ""
echo "🗑️  Step 2: Removing non-ready modules..."

# Get all llm_* directories except ready ones
ALL_MODULES=($(find . -maxdepth 1 -type d -name "llm_*" -exec basename {} \; | sort))

# Find modules to remove (all modules except ready ones)
MODULES_TO_REMOVE=()
for module in "${ALL_MODULES[@]}"; do
    # Check if module is in READY_MODULES array
    if [[ ! " ${READY_MODULES[*]} " =~ " ${module} " ]]; then
        MODULES_TO_REMOVE+=("$module")
    fi
done

echo "Modules to remove: ${MODULES_TO_REMOVE[*]}"

# Remove non-ready modules
for module in "${MODULES_TO_REMOVE[@]}"; do
    if [ -d "$module" ]; then
        echo "  🗑️  Removing $module"
        rm -rf "$module"
    fi
done

# Also remove any other non-essential files/directories that shouldn't be in 18.0
OTHER_TO_REMOVE=(
    "*.pyc"
    "__pycache__"
    ".pytest_cache"
    "*.log"
)

for pattern in "${OTHER_TO_REMOVE[@]}"; do
    find . -name "$pattern" -type f -delete 2>/dev/null || true
    find . -name "$pattern" -type d -exec rm -rf {} + 2>/dev/null || true
done

# Commit the cleanup
git add .
if ! git diff --staged --quiet; then
    git commit -m "feat: Remove non-ready modules from $SOURCE_BRANCH

Removed modules (not yet ready for 18.0):
$(printf '- %s\n' "${MODULES_TO_REMOVE[@]}")

Kept ready modules:
$(printf '- %s\n' "${READY_MODULES[@]}")

Total: ${#READY_MODULES[@]} modules ready for Odoo 18.0"
    echo "✅ Committed module cleanup"
else
    echo "ℹ️  No changes to commit"
fi

# Step 3: Create final 18.0 branch
echo ""
echo "🌿 Step 3: Creating $TARGET_BRANCH from $INTERMEDIATE_BRANCH..."

if git rev-parse --verify "$TARGET_BRANCH" > /dev/null 2>&1; then
    echo "⚠️  $TARGET_BRANCH already exists. Deleting and recreating..."
    git branch -D "$TARGET_BRANCH"
fi

git checkout -b "$TARGET_BRANCH"
echo "✅ Created $TARGET_BRANCH"

# Return to original branch
echo ""
echo "🔄 Returning to $CURRENT_BRANCH branch..."
git checkout "$CURRENT_BRANCH"

echo ""
echo "🎉 Branch creation completed successfully!"
echo ""
echo "📊 Summary:"
echo "  🔬 $CURRENT_BRANCH: Original work preserved"
echo "  🧪 $INTERMEDIATE_BRANCH: Staging branch with cleanup"
echo "  🚀 $TARGET_BRANCH: Production branch with ready modules"
echo ""
echo "📋 Ready modules in $TARGET_BRANCH:"
printf '  ✅ %s\n' "${READY_MODULES[@]}"
echo ""
echo "🔗 Next steps:"
echo "  1. Test modules: git checkout $TARGET_BRANCH"
echo "  2. Push when ready: git push origin $TARGET_BRANCH"
echo "  3. Continue development: git checkout $CURRENT_BRANCH"
echo "  4. Add modules later: git checkout $INTERMEDIATE_BRANCH -- module_name/"