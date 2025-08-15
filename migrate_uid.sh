#!/bin/bash
# deprecated, used only for migration
# https://sgel3iu6zt.feishu.cn/docx/Xy5nd2t2lo8JnqxROquc0vfBnzc?theme=LIGHT&contentTheme=DARK#MMEcd0hDCo7hFgxHKB2caIXHnib
# migrate uid gid
# before running this script: allow root ssh and login in root

UID_MAPPING="/mnt/data1/public/app/uid_mapping.csv"

groupmod --gid 2000 antnlp

while IFS="," read -r username uid activate; do
    if id "$username" >/dev/null 2>&1; then
        # user exists
        echo changing user $username ...
        pkill -9 -u $username # kill all process in order to usermod
        usermod -u $uid -g antnlp $username
        # umask is by default 002, but if group is antnlp, umask will be 022, making file permissions incorrect
        # remove group and other's write permission
        chmod -R go-w /home/$username
    fi
done < <(tail -n +2 $UID_MAPPING)

# also mod private folder, because usermod don't modify files outside /home
private=/mnt/data1/private/
for username in $(ls $private); do
    echo private folder permissions for $username ...
    chown -R $username:antnlp $private$username
    chmod -R go-w $private$username
done
