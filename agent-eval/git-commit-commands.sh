#!/bin/bash
# Git commit commands for agent evaluation framework
# Run this script from the agent-eval directory

set -e

echo "========================================="
echo "  Preparing Git Commit"
echo "========================================="
echo ""

# Ensure we're in the right directory
if [ ! -f "README.md" ] || [ ! -d "agent_eval" ]; then
    echo "Error: Must run from agent-eval directory"
    exit 1
fi

# Ensure we're on the right branch
CURRENT_BRANCH=$(git branch --show-current)
if [ "$CURRENT_BRANCH" != "agent-evaluation" ]; then
    echo "Error: Not on agent-evaluation branch (current: $CURRENT_BRANCH)"
    exit 1
fi

echo "✓ On branch: agent-evaluation"
echo ""

# Stage all new and modified files
echo "Staging files..."
echo ""

# Core implementation files
git add agent_eval/adapters/
git add agent_eval/evaluators/
git add agent_eval/judges/
git add agent_eval/providers/
git add agent_eval/schemas/
git add agent_eval/tools/
git add agent_eval/cli.py
git add agent_eval/pipeline.py

# Test files
git add agent_eval/tests/

# Test fixtures and expected results
git add test-fixtures/

# Scripts and automation
git add scripts/
git add Makefile

# Documentation
git add README.md
git add guides/
git add COMMIT_MESSAGE.txt

# Root-level updates
git add ../.gitignore

echo "✓ Files staged"
echo ""

# Show what will be committed
echo "========================================="
echo "  Files to be committed:"
echo "========================================="
git status --short
echo ""

# Commit with message from file
echo "========================================="
echo "  Creating commit..."
echo "========================================="
git commit -F COMMIT_MESSAGE.txt

echo ""
echo "✓ Commit created successfully!"
echo ""
echo "Next steps:"
echo "  1. Review commit: git show HEAD"
echo "  2. Push to remote: git push origin agent-evaluation"
echo ""
