#!/usr/bin/env python3
import os
import re
import sys


# 优化正则表达式，增强匹配鲁棒性
hit_re = re.compile(r"Trace 0x\w+ \[\d+: (\w+)\]\s*")


def get_hit_blocks(trace_file):
    """
    从trace文件中提取命中的块地址
    
    Args:
        trace_file (str): trace文件路径
    
    Returns:
        set: 命中的块地址（十进制整数）
    
    Raises:
        FileNotFoundError: 文件不存在时抛出
        PermissionError: 无文件读取权限时抛出
    """
    hit_blocks = set()
    
    # 检查文件是否存在
    if not os.path.exists(trace_file):
        raise FileNotFoundError(f"Trace文件不存在: {trace_file}")
    
    # 读取并解析文件
    with open(trace_file, 'r', encoding='utf-8') as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue  # 跳过空行
            
            m = hit_re.match(line)
            if m:
                try:
                    # 将十六进制字符串转为十进制整数
                    addr = int(m.group(1), 16)
                    hit_blocks.add(addr)
                except ValueError as e:
                    print(f"警告: 第{line_num}行的地址解析失败 - {e}", file=sys.stderr)
    
    return hit_blocks


if __name__ == '__main__':
    # 检查命令行参数
    if len(sys.argv) != 2:
        print("用法: python coverage.py <trace_file_path>", file=sys.stderr)
        sys.exit(1)
    
    trace_file_path = sys.argv[1]
    
    try:
        blocks = get_hit_blocks(trace_file_path)
        # 输出结果（Python3 print语法）
        print(f"Hit {len(blocks)} blocks:")
        # 排序后转为十六进制字符串，并用逗号连接
        hex_blocks = [hex(b) for b in sorted(blocks)]
        print(",".join(hex_blocks))
    except Exception as e:
        print(f"错误: {e}", file=sys.stderr)
        sys.exit(1)
