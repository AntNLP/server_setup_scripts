#!/bin/bash
# deprecated, used only for migration

set -euxo pipefail

for user in $(ls /home); do
    ln -sfn /nas/public "/home/$user/public"
    ln -sfn "/nas/data/$user" "/home/$user/data"
    if [[ ! -e "/home/$user/.conda" || -L "/home/$user/.conda" ]]; then
        ln -sfn "/home/$user/data/.conda" "/home/$user/.conda"
    fi
    chown -h "${user}":antnlp "/home/$user/"{public,data,.conda} # -h: change symlink itself, do not add trailing slash
    for idx in "" $(seq 2 5); do
        if [ -d "/mnt/local$idx" ]; then
            mkdir -p "/mnt/local$idx/$user" && chown "${user}":antnlp "/mnt/local$idx/$user"
            ln -sfn "/mnt/local$idx/$user" "/home/$user/local$idx"
            chown -h "${user}":antnlp "/home/$user/local$idx"
        else
            break
        fi
    done
done
