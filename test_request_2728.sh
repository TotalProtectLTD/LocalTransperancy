#!/bin/bash
# Test request for app_id 2728 (Cleaning Master for Your Phone)
# This reproduces the exact request that fails on the server

echo "Testing POST request to server..."
echo "URL: https://magictransparency.com/api/appmagic/apps/2728/metrics"
echo ""

curl -X POST "https://magictransparency.com/api/appmagic/apps/2728/metrics" \
  -H "X-Incoming-Secret: ad2a58397cf97c8bdf5814a95e33b2c17490933d9255e3e10d55ed36a665449e" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  -d @payload_to_server_2728_9583805.json \
  -v

echo ""
echo "Request completed"

