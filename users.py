#!/usr/bin/env python3

# - Create user if active but not found
# - Delete user (with prompting) if not active but exists
# - Do nothing if user exists but not in list
#
# If username starts with `#`, it is skipped (act as a comment)
# This is useful when some users are only active on several but not all machines,
# For example, run script w/o `#` on some machines, and add `#` when running on others
# Don't delete entries, keep the uid unique

import csv
import glob
import grp
import os
import pwd
import shlex
import subprocess
import sys
from typing import List, Optional, Union

from config import passwd_pattern

UID_MAPPING = "/nas/public/app/users/uid_mapping.csv"


def run_command(
    command: Union[str, List[str]],
    input_str: Optional[str] = None,
    suppress_errors: Optional[List[str]] = None,
    verbose: Union[bool, str] = False,
):
    try:
        if isinstance(command, str):
            command = shlex.split(command)
        if verbose:
            print(f"{verbose + ': ' if isinstance(verbose, str) else ''}{' '.join(command)}")
        result = subprocess.run(
            command,
            text=True,  # decode bytes to str
            input=input_str,  # pass input to command if any
            check=True,  # raise error if command fails
            stderr=subprocess.PIPE,  # capture stderr for filtering
        )

        # 处理输出
        if result.stderr:
            # 过滤需要忽略的错误
            filtered_stderr = []
            if suppress_errors:
                for line in result.stderr.splitlines():
                    if not any(error in line for error in suppress_errors):
                        filtered_stderr.append(line)
            else:
                filtered_stderr = result.stderr.splitlines()

            if filtered_stderr:
                stderr_output = "\n".join(filtered_stderr)
                print(f"{stderr_output}", end="", file=sys.stderr)

    except subprocess.CalledProcessError as e:
        print(f"Command failed: {' '.join(e.cmd)}", file=sys.stderr)
        if e.stderr is not None:
            print(e.stderr, end="", file=sys.stderr)
        exit(e.returncode)


def create_group():
    """创建 antnlp 组（如果不存在）"""
    try:
        grp.getgrnam("antnlp")
        print("group antnlp exists")
    except KeyError:
        print("creating group antnlp")
        run_command("groupadd --gid 2000 antnlp")


def user_exists(username):
    """检查用户是否存在"""
    try:
        pwd.getpwnam(username)
        return True
    except KeyError:
        return False


def get_user_primary_group(username):
    return pwd.getpwnam(username).pw_gid


def ask_confirm(prompt):
    """询问用户是否确认"""
    while True:
        confirm = input(prompt + " [y/N] ").strip().lower()
        if confirm in ["yes", "y"]:
            return True
        elif confirm in ["no", "n", ""]:
            return False
        else:
            print("Please enter y or n", file=sys.stderr)


def delete_user(username):
    """删除用户及其相关目录"""
    # 删除用户主目录
    run_command(f"userdel -r '{username}'", suppress_errors=["mail spool"])

    # 删除 /mnt/local 目录
    for local_path in glob.glob("/mnt/local*"):
        path = f"{local_path}/{username}"
        if os.path.exists(path):
            if ask_confirm(f"rm -rf '{path}' ?"):
                run_command(f"rm -rf '{path}'")


def create_user(username, uid):
    """创建新用户并设置环境"""
    # 创建用户
    run_command(
        f"useradd --uid {uid} --gid 2000 --shell /usr/bin/zsh --home-dir '/home/{username}' --create-home '{username}'",
    )

    # 设置密码
    password = passwd_pattern.format(username=username, uid=uid)
    run_command("chpasswd", input_str=f"{username}:{password}", suppress_errors=["BAD PASSWORD"])


def create_links(username, group="antnlp", local_only=False, verbose=False):
    """local_only: 用于为其他用户（非csv中列出的用户）创建local链接"""
    # 创建本地存储目录
    for local_path in glob.glob("/mnt/local*"):
        user_path = f"{local_path}/{username}"
        if not os.path.exists(user_path):
            os.makedirs(user_path, mode=0o755, exist_ok=True)
            if verbose:
                print(f"{verbose + ': ' if isinstance(verbose, str) else ''}mkdir -p {user_path}")
            run_command(f"chown '{username}:{group}' '{user_path}'")

        # Extract the suffix from the local path for the link name
        local_suffix = local_path.replace("/mnt/local", "")
        link_path = f"/home/{username}/local{local_suffix}"
        if not os.path.exists(link_path):
            run_command(f"ln -sfn '{user_path}' '{link_path}'", verbose=verbose)
            run_command(f"chown -h '{username}:{group}' '{link_path}'")

    if local_only:
        return

    # 创建NAS链接
    links = [  # (target, link, force)
        ("/nas/public", f"/home/{username}/public"),
        (f"/nas/data/{username}", f"/home/{username}/data"),
        (f"/home/{username}/data/.conda", f"/home/{username}/.conda"),
    ]
    for target, link in links:
        if not os.path.exists(link):
            run_command(f"ln -sfn '{target}' '{link}'", verbose=verbose)
            # -h: change symlink itself, do not add trailing slash
            run_command(f"chown -h '{username}:{group}' '{link}'")


def process_users():
    """处理所有用户账户"""
    users = set()  # 记录所有用户名

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
            users.add(username)

            if username.startswith("#"):
                print("skipping", username)
                users.add(username[1:].strip())
                continue

            if active == "1":
                if user_exists(username):
                    print(f"{username} is found")
                    create_links(username, verbose=f"Fixing link for {username}")
                else:
                    print(f"creating user {username} with uid {uid}")
                    create_user(username, uid)
                    create_links(username)
            else:
                if user_exists(username):
                    if ask_confirm(f"delete user {username}?"):
                        delete_user(username)
    return users


def fix_other_users(processed_users):
    for user in os.listdir("/home"):
        if user not in processed_users and user_exists(user):
            create_links(
                user,
                group=get_user_primary_group(user),
                local_only=True,
                verbose=f"Creating local link for {user}",
            )


if __name__ == "__main__":
    assert os.geteuid() == 0, "Error: This script must be run as root"
    assert os.path.isfile(UID_MAPPING), f"Error: UID mapping file not found at {UID_MAPPING}"

    create_group()
    users = process_users()
    fix_other_users(users)
