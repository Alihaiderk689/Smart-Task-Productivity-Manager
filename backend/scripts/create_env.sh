#!/usr/bin/env bash
set -e

if [ -f .env ]; then
  echo ".env already exists. Aborting."
  exit 1
fi

if [ ! -f .env.example ]; then
  echo "No .env.example found."
  exit 1
fi

cp .env.example .env
echo ".env created from .env.example"
