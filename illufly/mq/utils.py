import os
import platform
import tempfile
import logging
import zmq
import hashlib
from urllib.parse import urlparse

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

def normalize_address(address: str, default_address: str=None) -> str:
    """规范化地址格式，处理IPC地址长度限制"""
    if address.startswith("ipc://"):
        # 解析IPC路径
        path = urlparse(address).path
        if not path:
            raise ValueError("IPC path is required")
        # 计算最大允许长度（保留20字符给zmq内部使用）
        max_path_length = 87
        if len(path) > max_path_length:
            # 使用hash处理超长路径
            dir_path = os.path.dirname(path)
            file_name = os.path.basename(path)
            hashed_name = hashlib.md5(file_name.encode()).hexdigest()[:10] + ".ipc"
            
            # 如果目录路径也太长，使用临时目录
            if len(dir_path) > (max_path_length - len(hashed_name) - 1):
                dir_path = tempfile.gettempdir()
                
            path = os.path.join(dir_path, hashed_name)
            logging.warning(
                f"IPC path too long, truncated to: {path}"
            )            
        # 确保目录存在
        # os.makedirs(os.path.dirname(path), exist_ok=True)
        return f"ipc://{path}"            
    return address

def is_ipc(address):
    return address.startswith("ipc://")

def is_inproc(address):
    return address.startswith("inproc://") 

def is_tcp(address):
    return address.startswith("tcp://")

def exist_ipc_file(address):
    if is_ipc(address):
        path = urlparse(address).path
        return os.path.exists(path)
    return False

def init_bound_socket(context, socket_type,  address, logger) -> tuple[bool, zmq.Socket]:
    """初始化绑定socket
    
    Returns:
        tuple[bool, zmq.Socket]: 是否已绑定，socket
    """
    try:
        if exist_ipc_file(address):
            logger.warning(f"IPC file exists: {address}, treating as bound by another process")
            return (True, None)
        # 创建socket并尝试绑定
        socket = context.socket(socket_type)
        socket.bind(address)
        return (False, socket)
    except zmq.ZMQError as e:
        socket.close()  # 关闭失败的socket
        if e.errno == zmq.EADDRINUSE:
            logger.warning(f"Address {address} in use by another process")
            return (True, None)  # 标记为外部绑定
        else:
            raise

def cleanup_ipc_file(address, logger):
    """清理IPC文件"""
    if is_ipc(address):
        try:
            path = urlparse(address).path
            if os.path.exists(path):
                os.unlink(path)
        except Exception as e:
            logger.warning(f"Failed to remove IPC file: {e}")

def cleanup_bound_socket(socket, address, logger):
    """清理绑定socket"""
    if socket:
        socket.close()
        # 如果是IPC，删除文件
        cleanup_ipc_file(address, logger)
        socket = None

def cleanup_connected_socket(socket, address, logger):
    """清理连接socket"""
    if socket:
        socket.close()
        socket = None