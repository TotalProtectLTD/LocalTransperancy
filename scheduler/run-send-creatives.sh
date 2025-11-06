#!/bin/bash
# Wrapper script for send_incoming_creative.py
# This script is executed by launchd, which then calls the Python script

cd /Users/rostoni/Downloads/LocalTransperancy
exec /Library/Developer/CommandLineTools/Library/Frameworks/Python3.framework/Versions/3.9/bin/python3.9 send_incoming_creative.py --limit 10

