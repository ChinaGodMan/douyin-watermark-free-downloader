


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

def set_exif_time(filename, time_str, remark="SetTimeOk"):
    """设置EXIF时间，并写入自定义备注"""
    cmd = [
        'exiftool',
        '-AllDates=' + time_str,
        '-UserComment=' + remark,  # 新增写入备注
        '-overwrite_original',
        filename
    ]
    try:
        subprocess.run(cmd, check=True,
                     stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL)
        return True
    except subprocess.CalledProcessError:
        return False

def set_file_modification_time(filename, time_str):
    """设置文件修改时间"""
    try:
        dt = datetime.strptime(time_str, "%Y:%m:%d %H:%M:%S")
        timestamp = dt.timestamp()
        #os.utime(filename, (timestamp, timestamp))
        return True
    except Exception:
        return False

def get_file_modification_time(filename):
    """获取文件修改时间"""
    try:
        timestamp = os.path.getmtime(filename)
        return datetime.fromtimestamp(timestamp)
    except Exception:
        return None

def process_jpg_files():
    # 收集所有jpg文件
    # = [f for f in os.listdir('.') if f.endswith('.jpg')]
    jpg_files = [f for f in os.listdir('.') if f.endswith('.jpg') or f.endswith('.png')]
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
            datetime_str = extract_datetime_from_filename(filename)
            date_part, time_part = datetime_str.split('-')
            
            utc_time = datetime.strptime(f"{date_part} {time_part}", "%Y%m%d %H%M%S")
            local_time = utc_time + timedelta(hours=8)
            new_time = local_time.strftime("%Y:%m:%d %H:%M:%S")
            
            display_name = truncate_filename(filename)
            print(f"  {Colors.GREEN}[{idx}/{len(has_timestamp)}]{Colors.RESET} {Colors.BLUE}{display_name}{Colors.RESET}")
            print(f"    {Colors.CYAN}时间: {Colors.YELLOW}{new_time}{Colors.RESET}")
            
            if set_exif_time(filename, new_time):
                processed += 1
                total_processed += 1
            else:
                print(f"{Colors.RED}      错误: EXIF修改失败{Colors.RESET}")
    
    # ========== 第二部分：处理仅含ID的文件 ==========
    if has_id_only:
        print(f"\n{Colors.CYAN}=== 处理仅含ID的文件 (使用最旧的文件修改时间) ==={Colors.RESET}")
        
        # 按ID分组
        id_to_files = {}
        for filename in has_id_only:
            file_id = extract_id_from_filename(filename)
            if file_id:
                if file_id not in id_to_files:
                    id_to_files[file_id] = []
                id_to_files[file_id].append(filename)
        
        # 计算每个ID的最旧时间
        id_oldest_times = {}
        for file_id, files in id_to_files.items():
            file_times = []
            for filename in files:
                mtime = get_file_modification_time(filename)
                if mtime:
                    file_times.append((filename, mtime))
            
            if file_times:
                oldest_file, oldest_time = min(file_times, key=lambda x: x[1])
                id_oldest_times[file_id] = {
                    'time': oldest_time,
                    'file': oldest_file,
                    'files': files
                }
        
        # 处理不同ID之间的时间冲突
        used_times = set()
        sorted_ids = sorted(id_oldest_times.items())
        
        for id_idx, (file_id, info) in enumerate(sorted_ids, 1):
            base_time = info['time']
            files = info['files']
            oldest_file = info['file']
            
            # 检查这个ID的时间是否已被其他ID占用
            time_str = base_time.strftime("%Y:%m:%d %H:%M:%S")
            adjusted_time = base_time
            offset = 0
            
            while time_str in used_times:
                offset += 1
                adjusted_time = base_time + timedelta(seconds=offset)
                time_str = adjusted_time.strftime("%Y:%m:%d %H:%M:%S")
            
            # 把这个时间加入已使用集合
            used_times.add(time_str)
            
            print(f"\n  {Colors.MAGENTA}[ID {id_idx}/{len(id_oldest_times)}] {file_id}{Colors.RESET}")
            if offset > 0:
                print(f"    {Colors.YELLOW}⚠ 与其他ID时间冲突，整体偏移 +{offset}秒{Colors.RESET}")
            print(f"    {Colors.CYAN}使用时间: {Colors.YELLOW}{time_str}{Colors.RESET}")
            print(f"    {Colors.CYAN}来自文件: {Colors.BLUE}{truncate_filename(oldest_file)}{Colors.RESET}")
            print(f"    {Colors.CYAN}包含 {len(files)} 个文件 (全部使用同一时间){Colors.RESET}")
            
            # 这个ID下的所有文件都使用同一个时间
            for file_idx, filename in enumerate(files, 1):
                display_name = truncate_filename(filename)
                is_oldest = (filename == oldest_file)
                
                if is_oldest:
                    print(f"      {Colors.GREEN}[{file_idx}/{len(files)}]{Colors.RESET} {Colors.BLUE}{display_name}{Colors.RESET} {Colors.CYAN}← 最旧{Colors.RESET}")
                else:
                    print(f"      {Colors.GREEN}[{file_idx}/{len(files)}]{Colors.RESET} {Colors.BLUE}{display_name}{Colors.RESET}")
                    file_mtime = get_file_modification_time(filename)
                    if file_mtime:
                        print(f"        {Colors.CYAN}原时间: {Colors.YELLOW}{file_mtime.strftime('%Y:%m:%d %H:%M:%S')}{Colors.RESET}")
                
                # 修改EXIF和文件时间
                exif_success = set_exif_time(filename, time_str)
                filetime_success = set_file_modification_time(filename, time_str)
                
                if exif_success and filetime_success:
                    processed += 1
                    total_processed += 1
                    if not is_oldest:
                        print(f"        {Colors.CYAN}✓ 已更新为统一时间{Colors.RESET}")
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