#!/bin/bash -e

cd integration-tests
python3 -m venv venv
source venv/bin/activate
pip3 install -r requirements.txt
python3 -m unittest -v -f integration_tests 