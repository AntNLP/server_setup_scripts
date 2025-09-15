#!/bin/bash
# 配置参数
MOUNT_POINT="/nas"
TEST_FILE="${MOUNT_POINT}/.nas_healthcheck"
LOG_FILE="/var/log/nas_monitor.log"
LOCK_FILE="/var/lock/nas_monitor.lock"
NAS_IP="172.23.148.200"

# 确保日志文件存在且有正确权限
[[ -f "$LOG_FILE" ]] || { touch "$LOG_FILE"; chmod 640 "$LOG_FILE"; }

# 日志记录函数
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" >> "${LOG_FILE}"
}

# flock 防止重复执行脚本
exec 9>"${LOCK_FILE}"
if ! flock -n 9; then
    log "flock failed: Another instance is already running - exiting"
    exit 1
fi

# 检查NAS响应
check_nas_inner() {
    # 1. 检查基础网络连通性
    if ! ping -c1 -W2 "${NAS_IP}" >/dev/null 2>&1; then
        msg="network unreachable"
        return 1
    fi

    # 2. 检查NFS服务状态
    if ! timeout 5s rpcinfo -t "${NAS_IP}" nfs >/dev/null 2>&1; then
        msg="service not responding"
        return 1
    fi

    # 3. 测试文件操作（带超时）
    # if not mounted, MOUNT_POINT is local, touch will success
    if ! timeout 5s touch "${TEST_FILE}" >/dev/null 2>&1; then
        msg="file operation timed out"
        return 1
    fi
    
    return 0
}

# 如果失败，重试10次，每次间隔15秒；如果成功，直接返回
check_nas() {
    local max_attempts=10
    for attempt in $(seq 1 $max_attempts); do
        if check_nas_inner; then
            (( attempt > 1 )) && log "NAS check succeeded on attempt ${attempt}"
            return 0
        fi
        log "NAS check failed: ${msg} (attempt ${attempt}/${max_attempts})"
        sleep 15
    done
    return 1
}

# 检查挂载点状态
is_mounted() {
    timeout 5s mountpoint -q "${MOUNT_POINT}"
    ret=$?
    (( ret == 124 )) && ret=0  # 124 is timeout, treat as mounted
    return $ret
}

# 主逻辑
if check_nas; then
    # NAS可用
    if is_mounted; then
        # 已挂载且正常 - 无操作
        # log "NAS available and mounted - no action"
        :
    else
        # 未挂载但可用 - 尝试挂载
        log "NAS available but not mounted - mounting..."
        mount -a
        if is_mounted; then
            log "Mount successful"
        else
            log "Mount failed!"
        fi
    fi
else
    # NAS不可用
    if is_mounted; then
        # 已挂载但不可用 - 尝试卸载
        log "NAS unavailable but mounted - unmounting..."
        
        # 尝试正常卸载
        umount "${MOUNT_POINT}" 2>/dev/null
        
        # 检查是否卸载成功
        if is_mounted; then
            # 正常卸载失败 - 尝试强制卸载
            log "Normal umount failed - forcing lazy unmount"
            umount -l "${MOUNT_POINT}"
            
            # 检查最终状态
            if is_mounted; then
                log "Unmount failed completely!"
            else
                log "Unmounted successfully (lazy)"
            fi
        else
            log "Unmounted successfully"
        fi
    else
        # 未挂载且不可用 - 无操作
        log "NAS unavailable and not mounted - no action"
    fi
fi
