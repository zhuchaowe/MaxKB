#!/usr/bin/env python3
"""
双向同步脚本：在两个 mineru 目录之间进行文件同步
目录1: ~/Documents/felo/gptbase-parser/loader/mineru
目录2: /Users/moshui/Documents/felo/moshui/MaxKB/apps/common/handle/impl/mineru
"""

import os
import sys
import time
import shutil
import hashlib
import argparse
from pathlib import Path
from datetime import datetime
from typing import Set, Tuple, Optional
import subprocess

try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler
    WATCHDOG_AVAILABLE = True
except ImportError:
    WATCHDOG_AVAILABLE = False
    print("警告: watchdog 未安装，实时监控功能不可用")
    print("运行 'pip install watchdog' 来启用实时监控功能")

class DirectorySyncer:
    def __init__(self, dir1: str, dir2: str, verbose: bool = False):
        self.dir1 = Path(dir1).expanduser().resolve()
        self.dir2 = Path(dir2).expanduser().resolve()
        self.verbose = verbose
        self.exclude_patterns = {
            '__pycache__',
            '.DS_Store',
            '*.pyc',
            '*.pyo',
            '.git',
            '.idea',
            '.vscode',
            '*.swp',
            '*.swo',
            '*~'
        }
        
    def should_exclude(self, path: Path) -> bool:
        """检查文件或目录是否应该被排除"""
        name = path.name
        
        for pattern in self.exclude_patterns:
            if pattern.startswith('*'):
                if name.endswith(pattern[1:]):
                    return True
            elif pattern.endswith('*'):
                if name.startswith(pattern[:-1]):
                    return True
            elif name == pattern:
                return True
                
        return False
    
    def get_file_hash(self, filepath: Path) -> str:
        """计算文件的 MD5 哈希值"""
        hash_md5 = hashlib.md5()
        try:
            with open(filepath, "rb") as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    hash_md5.update(chunk)
            return hash_md5.hexdigest()
        except Exception as e:
            if self.verbose:
                print(f"无法计算 {filepath} 的哈希值: {e}")
            return ""
    
    def get_relative_files(self, directory: Path) -> Set[Path]:
        """获取目录中所有文件的相对路径集合"""
        files = set()
        for item in directory.rglob("*"):
            if self.should_exclude(item):
                continue
            if item.is_file():
                relative_path = item.relative_to(directory)
                files.add(relative_path)
        return files
    
    def sync_file(self, source: Path, dest: Path, relative_path: Path) -> bool:
        """同步单个文件"""
        source_file = source / relative_path
        dest_file = dest / relative_path
        
        try:
            dest_file.parent.mkdir(parents=True, exist_ok=True)
            
            if not dest_file.exists():
                shutil.copy2(source_file, dest_file)
                if self.verbose:
                    print(f"复制: {relative_path}")
                return True
            else:
                source_hash = self.get_file_hash(source_file)
                dest_hash = self.get_file_hash(dest_file)
                
                if source_hash != dest_hash:
                    source_mtime = source_file.stat().st_mtime
                    dest_mtime = dest_file.stat().st_mtime
                    
                    if source_mtime > dest_mtime:
                        shutil.copy2(source_file, dest_file)
                        if self.verbose:
                            print(f"更新: {relative_path} (源文件较新)")
                        return True
                    elif self.verbose:
                        print(f"跳过: {relative_path} (目标文件较新或相同)")
                        
        except Exception as e:
            print(f"错误同步 {relative_path}: {e}")
            return False
            
        return False
    
    def sync_directories(self) -> Tuple[int, int]:
        """执行双向同步"""
        print(f"\n开始同步...")
        print(f"目录1: {self.dir1}")
        print(f"目录2: {self.dir2}")
        print("-" * 60)
        
        files1 = self.get_relative_files(self.dir1)
        files2 = self.get_relative_files(self.dir2)
        
        all_files = files1 | files2
        synced_count = 0
        deleted_count = 0
        
        for rel_path in all_files:
            file1 = self.dir1 / rel_path
            file2 = self.dir2 / rel_path
            
            if file1.exists() and not file2.exists():
                if self.sync_file(self.dir1, self.dir2, rel_path):
                    synced_count += 1
                    print(f"→ {rel_path}")
                    
            elif file2.exists() and not file1.exists():
                if self.sync_file(self.dir2, self.dir1, rel_path):
                    synced_count += 1
                    print(f"← {rel_path}")
                    
            elif file1.exists() and file2.exists():
                hash1 = self.get_file_hash(file1)
                hash2 = self.get_file_hash(file2)
                
                if hash1 != hash2:
                    mtime1 = file1.stat().st_mtime
                    mtime2 = file2.stat().st_mtime
                    
                    if mtime1 > mtime2:
                        if self.sync_file(self.dir1, self.dir2, rel_path):
                            synced_count += 1
                            print(f"→ {rel_path} (更新)")
                    else:
                        if self.sync_file(self.dir2, self.dir1, rel_path):
                            synced_count += 1
                            print(f"← {rel_path} (更新)")
        
        return synced_count, deleted_count
    
    def watch(self):
        """启动文件监控"""
        if not WATCHDOG_AVAILABLE:
            print("错误: watchdog 模块未安装")
            print("请运行: pip install watchdog")
            return
            
        class SyncHandler(FileSystemEventHandler):
            def __init__(self, syncer):
                self.syncer = syncer
                self.last_sync = 0
                self.sync_delay = 1
                
            def on_any_event(self, event):
                if event.is_directory:
                    return
                    
                current_time = time.time()
                if current_time - self.last_sync > self.sync_delay:
                    path = Path(event.src_path)
                    if not self.syncer.should_exclude(path):
                        print(f"\n检测到变化: {path.name}")
                        self.syncer.sync_directories()
                        self.last_sync = current_time
        
        event_handler = SyncHandler(self)
        observer = Observer()
        observer.schedule(event_handler, str(self.dir1), recursive=True)
        observer.schedule(event_handler, str(self.dir2), recursive=True)
        observer.start()
        
        print(f"\n监控模式已启动...")
        print(f"正在监控两个目录的变化，按 Ctrl+C 退出")
        print("-" * 60)
        
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            observer.stop()
            print("\n监控已停止")
        observer.join()

def main():
    parser = argparse.ArgumentParser(
        description="双向同步两个 mineru 目录",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  %(prog)s                    # 执行一次同步
  %(prog)s --watch           # 启动实时监控模式
  %(prog)s --verbose         # 显示详细信息
  %(prog)s --dry-run         # 模拟运行，不实际同步
        """
    )
    
    parser.add_argument(
        "--watch", "-w",
        action="store_true",
        help="启动监控模式，实时同步文件变化"
    )
    
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="显示详细输出"
    )
    
    parser.add_argument(
        "--dry-run", "-n",
        action="store_true",
        help="模拟运行，只显示将要执行的操作"
    )
    
    parser.add_argument(
        "--dir1",
        default="~/Documents/felo/gptbase-parser/loader/mineru",
        help="第一个目录路径 (默认: ~/Documents/felo/gptbase-parser/loader/mineru)"
    )
    
    parser.add_argument(
        "--dir2",
        default="/Users/moshui/Documents/felo/moshui/MaxKB/apps/common/handle/impl/mineru",
        help="第二个目录路径"
    )
    
    args = parser.parse_args()
    
    syncer = DirectorySyncer(args.dir1, args.dir2, verbose=args.verbose)
    
    if not syncer.dir1.exists():
        print(f"错误: 目录不存在 - {syncer.dir1}")
        sys.exit(1)
        
    if not syncer.dir2.exists():
        print(f"错误: 目录不存在 - {syncer.dir2}")
        sys.exit(1)
    
    if args.dry_run:
        print("模拟运行模式 - 不会实际修改文件")
        syncer.verbose = True
    
    if args.watch:
        syncer.sync_directories()
        syncer.watch()
    else:
        synced, deleted = syncer.sync_directories()
        print("-" * 60)
        print(f"同步完成: {synced} 个文件已同步")
        if deleted > 0:
            print(f"         {deleted} 个文件已删除")

if __name__ == "__main__":
    main()