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
    MAGENTA = '\033[95m'
    RESET = '\033[0m'

def extract_datetime_from_filename(filename):
    """从文件名提取时间戳 (20251224-111009)"""
    match = re.search(r'(\d{8})-(\d{6})', filename)
    if match:
        return match.group(0)
    return None

def extract_id_from_filename(filename):
    """从文件名提取数字ID (YII_数字_photo)"""
    match = re.search(r'(\d+)_photo', filename)
    if match:
        return match.group(1)
    return None

def truncate_filename(filename, max_len=30):
    """截断文件名"""
    if len(filename) <= max_len:
        return filename
    return f"{filename[:15]}...{filename[-10:]}"

def set_exif_time(filename, time_str):
    """设置EXIF时间"""
    cmd = ['exiftool', '-AllDates=' + time_str, '-overwrite_original', filename]
    try:
        subprocess.run(cmd, check=True, 
                     stdout=subprocess.DEVNULL, 
                     stderr=subprocess.DEVNULL)
        return True
    except subprocess.CalledProcessError:
        return False

def set_file_modification_time(filename, time_str):
    """设置文件修改时间"""
    # 将 "2026:08:29 14:35:13" 转换为 "202608291435.13" 格式
    # 或直接使用 datetime 对象
    try:
        dt = datetime.strptime(time_str, "%Y:%m:%d %H:%M:%S")
        timestamp = dt.timestamp()
        os.utime(filename, (timestamp, timestamp))
        return True
    except Exception:
        return False

def process_jpg_files():
    # 收集所有jpg文件
    jpg_files = [f for f in os.listdir('.') if f.endswith('.jpg')]
    total = len(jpg_files)
    
    if total == 0:
        print(f"{Colors.RED}错误: 未找到任何JPG文件{Colors.RESET}")
        return
    
    # 分类文件
    has_timestamp = []
    has_id_only = []
    skipped_files = []
    
    print(f"{Colors.CYAN}正在扫描文件...{Colors.RESET}")
    for filename in jpg_files:
        has_time = extract_datetime_from_filename(filename)
        has_id = extract_id_from_filename(filename)
        
        if has_time:
            has_timestamp.append(filename)
        elif has_id:
            has_id_only.append(filename)
        else:
            skipped_files.append(filename)
    
    print(f"{Colors.GREEN}找到 {len(has_timestamp)} 个带时间戳的文件{Colors.RESET}")
    print(f"{Colors.BLUE}找到 {len(has_id_only)} 个仅含ID的文件{Colors.RESET}")
    if skipped_files:
        print(f"{Colors.YELLOW}跳过 {len(skipped_files)} 个不匹配格式的文件{Colors.RESET}")
    
    if not has_timestamp and not has_id_only:
        print(f"{Colors.RED}错误: 没有可处理的文件{Colors.RESET}")
        return
    
    processed = 0
    total_processed = 0
    
    # ========== 第一部分：处理带时间戳的文件 ==========
    if has_timestamp:
        print(f"\n{Colors.CYAN}=== 处理带时间戳的文件 (UTC→UTC+8) ==={Colors.RESET}")
        
        for idx, filename in enumerate(has_timestamp, 1):
            # 提取时间戳
            datetime_str = extract_datetime_from_filename(filename)
            date_part, time_part = datetime_str.split('-')
            
            # 解析UTC时间
            utc_time = datetime.strptime(f"{date_part} {time_part}", "%Y%m%d %H%M%S")
            
            # 转换为UTC+8
            local_time = utc_time + timedelta(hours=8)
            
            # 格式化为EXIF需要的格式
            new_time = local_time.strftime("%Y:%m:%d %H:%M:%S")
            
            display_name = truncate_filename(filename)
            print(f"  {Colors.GREEN}[{idx}/{len(has_timestamp)}]{Colors.RESET} {Colors.BLUE}{display_name}{Colors.RESET}")
            print(f"    {Colors.CYAN}时间: {Colors.YELLOW}{new_time}{Colors.RESET}")
            
            # 修改EXIF
            if set_exif_time(filename, new_time):
                processed += 1
                total_processed += 1
            else:
                print(f"{Colors.RED}      错误: EXIF修改失败{Colors.RESET}")
    
    # ========== 第二部分：处理仅含ID的文件 ==========
    if has_id_only:
        print(f"\n{Colors.CYAN}=== 处理仅含ID的文件 (使用当前时间) ==={Colors.RESET}")
        
        # 按ID分组
        id_to_files = {}
        for filename in has_id_only:
            file_id = extract_id_from_filename(filename)
            if file_id:
                if file_id not in id_to_files:
                    id_to_files[file_id] = []
                id_to_files[file_id].append(filename)
        
        # 为每个ID生成唯一时间
        base_time = datetime.now()
        
        for id_idx, (file_id, files) in enumerate(id_to_files.items(), 1):
            # 每个ID间隔1秒，确保唯一
            current_time = base_time + timedelta(seconds=id_idx)
            time_str = current_time.strftime("%Y:%m:%d %H:%M:%S")
            
            print(f"\n  {Colors.MAGENTA}[ID {id_idx}/{len(id_to_files)}] {file_id}{Colors.RESET}")
            print(f"    {Colors.CYAN}分配时间: {Colors.YELLOW}{time_str}{Colors.RESET}")
            print(f"    {Colors.CYAN}包含 {len(files)} 个文件{Colors.RESET}")
            
            for file_idx, filename in enumerate(files, 1):
                display_name = truncate_filename(filename)
                print(f"      {Colors.GREEN}[{file_idx}/{len(files)}]{Colors.RESET} {Colors.BLUE}{display_name}{Colors.RESET}")
                
                # 修改EXIF
                exif_success = set_exif_time(filename, time_str)
                
                # 修改文件修改时间
                filetime_success = set_file_modification_time(filename, time_str)
                
                if exif_success and filetime_success:
                    processed += 1
                    total_processed += 1
                    print(f"        {Colors.CYAN}✓ EXIF和文件时间已更新{Colors.RESET}")
                elif exif_success:
                    print(f"        {Colors.YELLOW}⚠ EXIF已更新，但文件时间修改失败{Colors.RESET}")
                    processed += 1
                    total_processed += 1
                else:
                    print(f"        {Colors.RED}✗ 修改失败{Colors.RESET}")
    
    # ========== 最终结果 ==========
    print(f"\n{Colors.GREEN}完成! 共处理 {total_processed} 个文件{Colors.RESET}")
    print(f"  {Colors.GREEN}✓ 带时间戳: {len(has_timestamp)} 个{Colors.RESET}")
    print(f"  {Colors.BLUE}✓ 仅含ID: {len(has_id_only)} 个{Colors.RESET}")
    if skipped_files:
        print(f"  {Colors.YELLOW}✗ 跳过: {len(skipped_files)} 个{Colors.RESET}")

if __name__ == "__main__":
    process_jpg_files()