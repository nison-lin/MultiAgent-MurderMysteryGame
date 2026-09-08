from datetime import datetime
import asyncio
import os
from pathlib import Path

class LogUtil:
    def __init__(self, log_path: str = ""):
        if log_path:
            os.makedirs(os.path.dirname(log_path), exist_ok=True)
            self.log_path = log_path
        else:
            default_path = str(Path(__file__).resolve().parent.parent)
            os.makedirs(default_path, exist_ok=True)
            self.log_path = os.path.join(default_path, 'log.txt')


    # 写入日志
    async def log(self, log: str):
        line = f'[{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}]  ' + log + '\n'
        await asyncio.to_thread(self._write, line)

    def _write(self, line: str):
        with open(self.log_path, 'a', encoding='utf-8') as f:
            f.write(line)


    # 写入警告日志
    async def warning(self, warning: str):
        await self.log("WARNING: " + warning)