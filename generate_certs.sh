#!/bin/bash

CERT_DIR="./certs"

# Create directory if it does not exist
mkdir -p $CERT_DIR

# Check if certs already exist
if [ ! -f "$CERT_DIR/key.pem" ] || [ ! -f "$CERT_DIR/cert.pem" ]; then
  openssl req -x509 -newkey rsa:4096 -keyout $CERT_DIR/key.pem -out $CERT_DIR/cert.pem -days 365 -nodes -subj "/C=US/ST=Denial/L=Earth/O=Dis/CN=timelord.tld"
fi
