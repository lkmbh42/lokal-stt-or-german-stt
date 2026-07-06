#!/usr/bin/env sh
# Generate a self-signed TLS certificate for the team server.
#
#   ./generate-self-signed.sh stt.team.internal [days]
#
# Produces cert.pem + key.pem in this directory (both git-ignored).
# For an internal CA instead: request a cert for the hostname and drop the
# PEM pair here under the same names — nginx config is identical.
set -eu

HOSTNAME="${1:?usage: $0 <hostname> [days]}"
DAYS="${2:-825}"
DIR="$(dirname "$0")"

openssl req -x509 -newkey rsa:2048 -nodes -sha256 \
  -keyout "$DIR/key.pem" -out "$DIR/cert.pem" -days "$DAYS" \
  -subj "/CN=$HOSTNAME" \
  -addext "subjectAltName=DNS:$HOSTNAME,DNS:localhost,IP:127.0.0.1"

chmod 600 "$DIR/key.pem"
echo "Wrote $DIR/cert.pem and $DIR/key.pem (CN=$HOSTNAME, $DAYS days)."
echo "Import cert.pem into client trust stores to avoid browser warnings."
