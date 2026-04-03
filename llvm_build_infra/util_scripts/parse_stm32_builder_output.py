"""
Script that converts STM32 build compilation output
to nice json output.
This json could be used to get bitcode files for the corresponding targets.
"""
import argparse
import os
import sys
import json
import re
from typing import List, Dict


def log_info(*args):
    log_str = "[*] "
    for curr_a in args:
        log_str = log_str + " " + str(curr_a)
    print(log_str)


def log_error(*args):
    log_str = "[!] "
    for curr_a in args:
        log_str = log_str + " " + str(curr_a)
    print(log_str)


def log_warning(*args):
    log_str = "[?] "
    for curr_a in args:
        log_str = log_str + " " + str(curr_a)
    print(log_str)


def log_success(*args):
    log_str = "[+] "
    for curr_a in args:
        log_str = log_str + " " + str(curr_a)
    print(log_str)


def setup_args():
    parser = argparse.ArgumentParser(
        description="Convert STM32 build output to compile_commands.json format"
    )
    parser.add_argument('-i', dest='builder_output',
                        help='Path to the STM32 build output file',
                        required=True)
    parser.add_argument('-o', dest='compile_commands_out',
                        default="compile_commands.json",
                        help='Path to the output compile_commands.json file (default: compile_commands.json)')
    parser.add_argument('-w', dest='used_work_dir',
                        default=os.getcwd(),
                        help='Working directory used for running STM32 build command (default: current directory)')
    return parser


def usage():
    log_error("Invalid Usage.")
    log_error(f"Run: python {__file__} --help to know the correct usage.")
    sys.exit(-1)


def safe_decode_file(file_path: str) -> List[str]:
    """
    安全读取文件：自动适配编码（UTF-8/GBK/GB2312），解决中文注释编码冲突问题
    """
    encodings = ['utf-8', 'gbk', 'gb2312', 'latin-1']
    for encoding in encodings:
        try:
            with open(file_path, 'r', encoding=encoding) as f:
                lines = [line.strip() for line in f.readlines() if line.strip()]
            log_info(f"Successfully read file with encoding: {encoding}")
            return lines
        except (UnicodeDecodeError, IOError):
            continue
    
    # 终极兜底：二进制模式读取后强制解码（忽略错误）
    try:
        with open(file_path, 'rb') as f:
            content = f.read()
        lines = content.decode('utf-8', errors='ignore').splitlines()
        lines = [line.strip() for line in lines if line.strip()]
        log_warning("Read file with binary mode (ignored decode errors)")
        return lines
    except Exception as e:
        log_error(f"Failed to read file even in binary mode: {e}")
        sys.exit(-1)


def is_known_compiler(curr_com: str) -> bool:
    """增强版：检查命令是否包含已知编译器（适配路径/别名）"""
    known_compilers = ['arm-none-eabi-gcc', 'arm-none-eabi-g++', 'gcc', 'g++']
    # 兼容带路径的编译器（如 /usr/bin/arm-none-eabi-gcc）
    return any(compiler in curr_com for compiler in known_compilers)


def process_builder_output(output_file: str) -> List[str]:
    """增强版：提取STM32编译命令（适配极简裸机编译输出）"""
    # 核心修复：使用安全解码函数读取文件，解决编码冲突
    all_lines = safe_decode_file(output_file)

    # 方案1：匹配包含 arm-none-eabi-gcc 的任意行（放宽过滤条件）
    compiler_lines = []
    # 匹配gcc编译c文件的命令（包含 -c 参数和 .c 文件）
    gcc_pattern = re.compile(r'arm-none-eabi-gcc.*-c.*\.c', re.IGNORECASE)
    # 匹配完整编译命令行（处理多行拼接的情况）
    multi_line_cmd = ""
    
    for line in all_lines:
        # 处理多行拼接的命令（以 \ 结尾）
        if line.endswith("\\"):
            multi_line_cmd += line.rstrip("\\")
            continue
        elif multi_line_cmd:
            multi_line_cmd += line
            line = multi_line_cmd
            multi_line_cmd = ""
        
        # 提取编译命令
        if gcc_pattern.search(line):
            compiler_lines.append(line.strip())
        # 兜底：匹配任何包含arm-none-eabi-gcc的行
        elif "arm-none-eabi-gcc" in line and "-c" in line:
            compiler_lines.append(line.strip())

    # 去重 + 过滤空命令
    compilation_lines = list(set([line for line in compiler_lines if line]))
    log_info(f"提取到 {len(compilation_lines)} 条STM32编译命令")
    
    # 打印提取到的命令（调试用）
    for i, cmd in enumerate(compilation_lines):
        log_info(f"编译命令 {i+1}: {cmd[:200]}..." if len(cmd) > 200 else f"编译命令 {i+1}: {cmd}")

    return compilation_lines


def get_json_string(compilation_line: str, work_dir: str) -> Dict:
    """增强版：解析编译命令为compile_commands.json格式（适配裸机参数）"""
    # 处理裸机编译的特殊参数（如 -ffreestanding -nostdlib）
    # 拆分命令参数（不拆分转义空格）
    cmd_parts = re.split(r'(?<!\\) ', compilation_line)
    
    # 提取编译器名称
    compiler_name = "arm-none-eabi-gcc" if "arm-none-eabi-gcc" in cmd_parts[0] else cmd_parts[0]
    
    # 提取输入文件（-c 参数后的值）
    input_files = []
    output_files = []
    for i, part in enumerate(cmd_parts):
        if part == "-c" and i+1 < len(cmd_parts):
            input_file = cmd_parts[i+1].strip()
            if input_file.endswith(".c"):
                # 处理相对路径/绝对路径
                if not os.path.isabs(input_file):
                    input_file = os.path.join(work_dir, input_file)
                input_files.append(os.path.abspath(input_file))
        elif part == "-o" and i+1 < len(cmd_parts):
            output_file = cmd_parts[i+1].strip()
            if not os.path.isabs(output_file):
                output_file = os.path.join(work_dir, output_file)
            output_files.append(os.path.abspath(output_file))

    # 兜底：从命令末尾提取输入文件
    if not input_files:
        c_file_match = re.search(r'(\S+\.c)', compilation_line)
        if c_file_match:
            input_file = c_file_match.group(1)
            if not os.path.isabs(input_file):
                input_file = os.path.join(work_dir, input_file)
            input_files.append(os.path.abspath(input_file))

    # 构造标准compile_commands格式
    return {
        "directory": os.path.abspath(work_dir),
        "command": compilation_line,
        "file": input_files[0] if input_files else "",
        "output": output_files[0] if output_files else "",
        "compiler": compiler_name,
        "arguments": cmd_parts
    }


def main():
    arg_parser = setup_args()
    try:
        parsed_args = arg_parser.parse_args()
    except argparse.ArgumentError:
        usage()

    # 校验输入
    input_file = parsed_args.builder_output
    output_file = parsed_args.compile_commands_out
    work_dir = parsed_args.used_work_dir

    if not os.path.isfile(input_file):
        log_error(f"输入文件不存在: {input_file}")
        usage()

    if not os.path.isdir(work_dir):
        log_error(f"工作目录不存在: {work_dir}")
        usage()

    # 日志配置
    log_info("="*50)
    log_info("STM32编译命令解析工具 v2.0 (修复编码问题)")
    log_info("="*50)
    log_info(f"输入构建输出文件: {input_file}")
    log_info(f"工作目录: {work_dir}")
    log_info(f"输出JSON文件: {output_file}")
    log_info("="*50)

    # 处理输出
    log_info("开始解析STM32构建输出...")
    compilation_lines = process_builder_output(input_file)
    
    if not compilation_lines:
        log_warning("未提取到任何STM32编译命令！")
        compile_commands = []
    else:
        log_info("转换为compile_commands.json格式...")
        compile_commands = [get_json_string(line, work_dir) for line in compilation_lines]

    # 写入输出（确保UTF-8编码，兼容中文路径）
    try:
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(compile_commands, f, ensure_ascii=False, sort_keys=True, indent=2)
        log_success(f"成功写入 {len(compile_commands)} 条编译命令到 {output_file}")
        # 打印输出文件路径
        log_info(f"编译命令JSON文件路径: {os.path.abspath(output_file)}")
    except IOError as e:
        log_error(f"写入输出文件失败: {e}")
        sys.exit(-2)

    log_info("="*50)
    log_success("STM32编译命令解析完成！")
    log_info("="*50)


if __name__ == "__main__":
    main()
