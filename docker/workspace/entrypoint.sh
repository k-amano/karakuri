#!/bin/bash
set -e

# Configure git if user info is provided
if [ -n "$GIT_USER_NAME" ]; then
    git config --global user.name "$GIT_USER_NAME"
fi

if [ -n "$GIT_USER_EMAIL" ]; then
    git config --global user.email "$GIT_USER_EMAIL"
fi

# Set git to use main as default branch
git config --global init.defaultBranch main

# Execute the command
exec "$@"
