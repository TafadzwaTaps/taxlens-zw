#!/usr/bin/env bash
# build.sh — executed by Render during deployment.
# Installs Tesseract OCR (system package) then Python dependencies.
set -e

echo "━━━ Installing Tesseract OCR ━━━"
apt-get update -qq
apt-get install -y -qq tesseract-ocr tesseract-ocr-eng libglib2.0-0 libsm6 libxext6

echo "━━━ Installing Python packages ━━━"
pip install --upgrade pip
pip install -r requirements.txt

echo "━━━ Build complete ✓ ━━━"
