#!/bin/bash

set -euo pipefail
# should run as root
if [[ $EUID -ne 0 ]]; then
    echo "This script must be run as root, try:"
    echo "sudo $0"
    exit 1
fi
cd "$(dirname "$0")"

update() {
    local src=$1
    local tgt=$2
    # if modify time different, update
    if [[ ! -f "$tgt" ]] || [[ $(stat -c %Y "$src") -gt $(stat -c %Y "$tgt") ]]; then
        mkdir -p "$(dirname "$tgt")"
        cp -v "$src" "$tgt" && chown root:root "$tgt"
    else
        echo "skip $src"
    fi
}

# NAS setup
update "users.py" "/nas/public/app/users/users.py"
update "config.py" "/nas/public/app/users/config.py"
update "nas_users.py" "/nas/public/app/users/nas_users.py"

# local setup
update "feishu_msg" "/usr/local/bin/feishu_msg"
update "feishu_msg_secrets.py" "/usr/local/bin/feishu_msg_secrets.py"
update "dcgm-counters.csv" "/etc/dcgm-exporter/dcgm-counters.csv"
update "nas_monitor.sh" "/usr/local/bin/nas_monitor.sh"
update "my_log" "/etc/logrotate.d/my_log"
update "my_cron" "/etc/cron.d/my_cron"
