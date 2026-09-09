#!/bin/bash
# Vendored from nextcloud/HaRP (exapps_dev/start.sh), AGPL-3.0-or-later,
# 2025 Nextcloud GmbH and contributors. The entrypoint for HaRP support:
# when a HaRP deploy daemon injects HP_SHARED_KEY, it writes an frpc
# config and starts the FRP client (tunnelling APP_PORT to the unix
# socket /tmp/exapp.sock that the app listens on), then execs the app.
# Without HP_SHARED_KEY (DSP / docker-socket-proxy / manual-install) it
# is a no-op pass-through and the app listens on TCP APP_HOST:APP_PORT.
# Upstream: https://github.com/nextcloud/HaRP/blob/main/exapps_dev/start.sh
# Divergences from upstream: frpc config is written to /tmp/frpc.toml
# (not /frpc.toml) so the image can run as a non-root user, and the
# launch banner uses $* instead of $@ (shellcheck SC2145).

set -e

# Only create a config file if HP_SHARED_KEY is set.
if [ -n "$HP_SHARED_KEY" ]; then
    echo "HP_SHARED_KEY is set, creating /tmp/frpc.toml configuration file..."
    if [ -d "/certs/frp" ]; then
        echo "Found /certs/frp directory. Creating configuration with TLS certificates."
        cat <<EOF > /tmp/frpc.toml
serverAddr = "$HP_FRP_ADDRESS"
serverPort = $HP_FRP_PORT
loginFailExit = false

transport.tls.enable = true
transport.tls.certFile = "/certs/frp/client.crt"
transport.tls.keyFile = "/certs/frp/client.key"
transport.tls.trustedCaFile = "/certs/frp/ca.crt"
transport.tls.serverName = "harp.nc"

metadatas.token = "$HP_SHARED_KEY"

[[proxies]]
remotePort = $APP_PORT
type = "tcp"
name = "$APP_ID"
[proxies.plugin]
type = "unix_domain_socket"
unixPath = "/tmp/exapp.sock"
EOF
    else
        echo "Directory /certs/frp not found. Creating configuration without TLS certificates."
        cat <<EOF > /tmp/frpc.toml
serverAddr = "$HP_FRP_ADDRESS"
serverPort = $HP_FRP_PORT
loginFailExit = false

transport.tls.enable = false

metadatas.token = "$HP_SHARED_KEY"

[[proxies]]
remotePort = $APP_PORT
type = "tcp"
name = "$APP_ID"
[proxies.plugin]
type = "unix_domain_socket"
unixPath = "/tmp/exapp.sock"
EOF
    fi
else
    echo "HP_SHARED_KEY is not set. Skipping FRP configuration."
fi

# If we have a configuration file and the shared key is present, start the FRP client
if [ -f /tmp/frpc.toml ] && [ -n "$HP_SHARED_KEY" ]; then
    echo "Starting frpc in the background..."
    frpc -c /tmp/frpc.toml &
fi

# Start the main application (launch cmd for ExApp is an argument for this script)
echo "Starting application: $*"
exec "$@"
