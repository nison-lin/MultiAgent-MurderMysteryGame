"""日志工具"""

from datetime import datetime
import os
from pathlib import Path

class LogUtil:
    """日志工具类"""
    
    def __init__(self, log_path: str = ""):
        if log_path:
            directory = os.path.dirname(os.path.abspath(log_path))
            os.makedirs(directory, exist_ok=True)
            self.log_path = log_path
        else:
            default_path = str(Path(__file__).resolve().parent.parent)
            os.makedirs(os.path.join(default_path, "logs"), exist_ok=True)
            self.log_path = os.path.join(default_path, 'log.txt')


    # 写入日志
    def log(self, log: str):
        line = f'[{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}]  ' + log + '\n'
        self._write(line)

    def _write(self, line: str):
        with open(self.log_path, 'a', encoding='utf-8') as f:
            f.write(line)


    # 写入警告日志
    def warning(self, warning: str):
        self.log("WARNING: " + warning)