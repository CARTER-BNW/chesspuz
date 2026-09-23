#!/usr/bin/env bash
# One-time: the release signing key for chesspuz (run inside the build box as root; sync.py setup
# calls it). The password is generated here and written only to ~/chesspuz-release.env in the box
# plus a backup of key and env file in D:\Claude\secrets\chesspuz-android; it is never printed.
# Losing the key means the next release cannot update an installed app (uninstall first).
set -euo pipefail
KS="$HOME/chesspuz-release.keystore"
ENV="$HOME/chesspuz-release.env"
SECRETS="/mnt/d/Claude/secrets/chesspuz-android"
if [ -f "$KS" ] && [ -f "$ENV" ]; then
    echo "keystore already exists: $KS"
elif [ -f "$SECRETS/chesspuz-release.keystore" ] && [ -f "$SECRETS/chesspuz-release.env" ]; then
    cp -f "$SECRETS/chesspuz-release.keystore" "$KS"
    cp -f "$SECRETS/chesspuz-release.env" "$ENV"
    chmod 600 "$ENV"
    echo "keystore restored from $SECRETS"
else
    PASS=$(openssl rand -hex 20)
    keytool -genkeypair -v -keystore "$KS" -alias chesspuz -keyalg RSA -keysize 2048 -validity 10000 \
        -storepass "$PASS" -keypass "$PASS" -dname "CN=John Carter, O=chesspuz, C=US" >/dev/null 2>&1
    cat > "$ENV" <<EOT
export P4A_RELEASE_KEYSTORE="$KS"
export P4A_RELEASE_KEYSTORE_PASSWD="$PASS"
export P4A_RELEASE_KEYALIAS_PASSWD="$PASS"
export P4A_RELEASE_KEYALIAS="chesspuz"
EOT
    chmod 600 "$ENV"
    echo "created $KS and $ENV"
fi
mkdir -p "$SECRETS" && cp -f "$KS" "$ENV" "$SECRETS/"
echo "backup in $SECRETS"
