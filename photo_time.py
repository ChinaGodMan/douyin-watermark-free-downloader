#!/usr/bin/env python3
import os
import re
from datetime import datetime, timedelta
import subprocess

# 颜色定义
class Colors:
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    RED = '\033[91m'
    RESET = '\033[0m'

def truncate_filename(filename, max_len=30):
    """截断文件名，保留开头和结尾"""
    if len(filename) <= max_len:
        return filename
    return f"{filename[:15]}...{filename[-10:]}"

def process_jpg_files():
    # 先收集所有jpg文件
    jpg_files = [f for f in os.listdir('.') if f.endswith('.jpg')]
    total = len(jpg_files)
    
    if total == 0:
        print(f"{Colors.RED}错误: 未找到任何JPG文件{Colors.RESET}")
        return
    
    processed = 0
    skipped = 0
    
    for idx, filename in enumerate(jpg_files, 1):
        # 提取时间戳
        match = re.search(r'(\d{8})-(\d{6})', filename)
        if not match:
            print(f"{Colors.YELLOW}[{idx}/{total}] 跳过: {Colors.RESET}{truncate_filename(filename)} {Colors.YELLOW}(未找到时间戳){Colors.RESET}")
            skipped += 1
            continue
        
        date_part, time_part = match.groups()
        datetime_str = f"{date_part} {time_part}"
        
        # 解析UTC时间
        utc_time = datetime.strptime(datetime_str, "%Y%m%d %H%M%S")
        
        # 转换为UTC+8
        local_time = utc_time + timedelta(hours=8)
        
        # 格式化为EXIF需要的格式
        new_time = local_time.strftime("%Y:%m:%d %H:%M:%S")
        
        # 显示进度（文件名截断，各部分不同颜色）
        display_name = truncate_filename(filename)
        print(f"{Colors.CYAN}正在处理图片: {Colors.GREEN}[{idx}/{total}] {Colors.BLUE}{display_name} {Colors.CYAN}-> {Colors.YELLOW}{new_time}{Colors.RESET}")
        
        # 修改EXIF - 静默执行
        cmd = ['exiftool', '-AllDates=' + new_time, '-overwrite_original', filename]
        try:
            subprocess.run(cmd, check=True, 
                         stdout=subprocess.DEVNULL, 
                         stderr=subprocess.DEVNULL)
            processed += 1
        except subprocess.CalledProcessError:
            print(f"{Colors.RED}  错误: 修改失败{Colors.RESET}")
            skipped += 1
    
    # 最终结果 - 绿色
    print(f"\n{Colors.GREEN}完成! 共处理 {total} 张图片 (成功: {processed}, 跳过: {skipped}){Colors.RESET}")

if __name__ == "__main__":
    process_jpg_files()