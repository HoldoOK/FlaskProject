#!/bin/bash
echo "=== Installing dependencies ==="
pip install -r requirements.txt

echo "=== Creating directories ==="
mkdir -p /tmp/uploads
mkdir -p static/uploads

echo "=== Build complete ==="