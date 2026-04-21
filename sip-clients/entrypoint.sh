#!/bin/bash
set -e

ROLE="${SIP_ROLE:-bob}"
PBX_HOST="${PBX_HOST:-asterisk-pbx}"
PBX_PORT="${PBX_PORT:-5060}"
SIP_USER="${SIP_USER:-$ROLE}"
SIP_PASS="${SIP_PASS:-${ROLE}123}"

CONFIG_DIR="/root/.baresip"
mkdir -p "$CONFIG_DIR"

# Write baresip accounts file
cat > "$CONFIG_DIR/accounts" <<EOF
<sip:${SIP_USER}@${PBX_HOST};transport=udp>;auth_pass=${SIP_PASS};answermode=auto;regint=60
EOF

# Write baresip config
cat > "$CONFIG_DIR/config" <<EOF
# SIP
sip_listen      0.0.0.0:5060

# Module path
module_path     /usr/lib/baresip/modules

# Audio - sine tone source, null player
audio_player    aufile,/dev/null
audio_source    ausine,440
audio_alert     aufile,/dev/null

# Modules
module          stdio.so
module          account.so
module          aufile.so
module          ausine.so
module          g711.so
module          stun.so
module          uuid.so
module          menu.so

# Audio settings
audio_buffer    20-160
audio_srate     8000
audio_channels  1
EOF

echo "Starting ${ROLE} (baresip)..."
echo "  SIP User: ${SIP_USER}"
echo "  PBX Host: ${PBX_HOST}:${PBX_PORT}"

# Start baresip in the foreground
exec baresip -f "$CONFIG_DIR" -v
