#!/usr/bin/env python3

# - Create user if active but not found
# - TODO: Delete user (with prompting) if not active but exists
# - Do nothing if user exists but not in list

import csv
import os
import shlex
import subprocess
import sys
from typing import List, Union

PUBLIC_DIR = "/mnt/truenas/nas/public"
DATA_DIR = "/mnt/truenas/nas/data"
UID_MAPPING = f"{PUBLIC_DIR}/app/users/uid_mapping.csv"
SKEL_DIR = f"{PUBLIC_DIR}/app/etc_skel"


def run_command(command: Union[str, List[str]], check=True) -> int:
    try:
        if isinstance(command, str):
            command = shlex.split(command)
        result = subprocess.run(
            command,
            text=True,  # decode bytes to str
            check=check,  # check: raise error if command fails, not check: no output and use returncode
            capture_output=not check,  # drop output if not check
        )
        return result.returncode

    except subprocess.CalledProcessError as e:
        print(f"Command failed: {' '.join(e.cmd)}", file=sys.stderr)
        if e.stdout is not None:
            print(e.stdout, end="")
        if e.stderr is not None:
            print(e.stderr, end="", file=sys.stderr)
        exit(e.returncode)


def run_cli(command: str, check=True) -> bool:
    assert "'" not in command, f'always use " in TrueNAS CLI command: {command}'
    return run_command(["cli", "-c", command], check=check)


def user_exists(uid: str) -> bool:
    return run_cli(f'account user get_user_obj get_user_obj={{"uid": {uid}}}', check=False)


def create_user(username: str, uid: str):
    # 用户不设置密码，ssh服务中永久关闭密码登录，用户可以在其他节点配置ssh key
    run_cli(
        f'account user create uid={uid} username="{username}" group="antnlp" '
        f'full_name="{username}" home="{DATA_DIR}" home_mode=755 '
        'home_create=true shell="/usr/bin/zsh" password_disabled=true smb=false'
    )


def set_quota(uid: str):
    """为用户设置5TB存储配额"""
    run_cli(
        'storage dataset set_quota ds="truenas/nas" '
        f'quotas=[{{"quota_type": "USER", "id": {uid}, "quota_value": 5497558138880}}]'
    )


def setup_home_directory(username: str):
    user_dir = os.path.join(DATA_DIR, username)

    # copy home default files
    # TrueNAS raises `Error: IsADirectoryError(21, 'Is a directory')` when copy dir in /etc/skel
    run_command(f"cp -RT '{SKEL_DIR}' '{user_dir}'")

    conda_dir = os.path.join(user_dir, ".conda")
    os.makedirs(conda_dir, mode=0o755, exist_ok=True)

    run_command(f"chown -R '{username}:antnlp' '{user_dir}'")


def process_users():
    with open(UID_MAPPING, "r") as f:
        reader = csv.reader(f)
        next(reader)  # 跳过标题行

        for row in reader:
            if not row:
                continue
            if not (3 <= len(row) <= 4 and all(row[:3])):  # comment can be empty
                print("broken row:", row)
                continue

            username, uid, active = [s.strip() for s in row[:3]]

            if username.startswith("#"):  # skipped in users.py but truenas script always check all users
                # remove leading `#`
                username = username[1:].strip()
                print("TrueNAS script doesn't skip user", username)

            if active == "1":
                if user_exists(uid):
                    print(f"{username} is found")
                else:
                    print(f"creating user {username} with uid {uid}")
                    create_user(username, uid)
                    set_quota(uid)
                    setup_home_directory(username)
            else:
                if user_exists(uid):
                    # TODO: remove user
                    print(f"{username} exists but not active, please remove manually")


if __name__ == "__main__":
    assert os.geteuid() == 0, "Error: This script must be run as root"
    assert os.path.exists(SKEL_DIR), SKEL_DIR
    assert os.path.isfile(UID_MAPPING), f"Error: UID mapping file not found at {UID_MAPPING}"

    process_users()
