import logging
import importlib.resources
import tempfile
import shutil
from pathlib import Path

class StaticFilesManager:
    """静态文件管理器"""
    def __init__(self, package="illufly", static_dir="api/static"):
        self.package = package
        self.static_dir = static_dir
        self._temp_dir = None
        self._logger = logging.getLogger(__name__)

    def setup(self) -> Path:
        """设置静态文件目录
        
        如果是开发环境，直接使用包内目录
        如果是安装环境，复制到临时目录
        """
        try:
            # 如果是zip包安装，需要解压到临时目录
            self._temp_dir = tempfile.mkdtemp(prefix="illufly_static_")
            temp_static = Path(self._temp_dir)
            
            # 复制所有静态文件到临时目录
            with importlib.resources.files(self.package).joinpath(self.static_dir) as static_path:
                self._logger.debug(f"拷贝资源目录: {static_path}")
                for file_path in static_path.rglob("*"):
                    if file_path.is_file():
                        rel_path = file_path.relative_to(static_path)
                        dest_path = temp_static / rel_path
                        dest_path.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(file_path, dest_path)
                        self._logger.debug(f"拷贝文件: {dest_path}")
            
            self._logger.debug(f"静态文件已复制到临时目录: {temp_static}")
            return temp_static
            
        except Exception as e:
            self._logger.warning(f"静态文件设置失败: {e}")
            return None
            
    def cleanup(self):
        """清理临时文件"""
        if self._temp_dir and Path(self._temp_dir).exists():
            shutil.rmtree(self._temp_dir)
            self._logger.warning(f"已清理临时目录: {self._temp_dir}")
