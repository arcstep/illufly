import os
import platform
import tempfile
import logging
import zmq

def get_ipc_path(name: str) -> str:
    """根据操作系统获取合适的 IPC 路径
    
    Args:
        name: IPC 连接的名称
        
    Returns:
        str: 格式化后的 IPC 地址
    """
    system = platform.system().lower()
    
    if system == "windows":
        # Windows 使用命名管道
        pipe_path = f"ipc://\\\\.\\pipe\\{name}"
        logging.debug(f"Using Windows named pipe: {pipe_path}")
        return pipe_path[0:zmq.IPC_PATH_MAX_LEN]
    else:
        # Unix-like 系统 (Linux, macOS)
        temp_dir = tempfile.gettempdir()
        ipc_path = os.path.join(temp_dir, f"{name}.ipc")
        
        # 确保路径存在且有正确的权限
        try:
            if os.path.exists(ipc_path):
                os.remove(ipc_path)
            os.makedirs(os.path.dirname(ipc_path), exist_ok=True)
        except (OSError, IOError) as e:
            logging.warning(f"Failed to prepare IPC path: {e}")
            raise  # 不再降级到 TCP，而是直接报错
            
        return f"ipc://{ipc_path[0:zmq.IPC_PATH_MAX_LEN]}" 