#!/usr/bin/env bash
set -euo pipefail

# Build and run the project via docker-compose for local development
docker-compose up --build --remove-orphans
