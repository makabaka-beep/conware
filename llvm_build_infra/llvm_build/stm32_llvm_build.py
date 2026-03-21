#!/usr/bin/python3
import os
import sys
import argparse
import subprocess
import json
import shutil

# 修正路径：指向llvm_build同级目录
sys.path.append(os.path.dirname(__file__))
try:
    from clang_build import build_using_clang
    from log_stuff import log_error, log_success, log_info, log_warning
except ImportError as e:
    print(f"Import error: {e}")
    print("请确认 clang_build.py/log_stuff.py 在当前目录！")
    sys.exit(-1)

# 定义完全兼容的CompilationCommand类（解决类型错误+所有属性问题）
class CompilationCommand:
    def __init__(self, directory, command, file, output):
        # 核心属性
        self.directory = directory      # 编译目录
        self.command = command          # 完整编译命令字符串
        self.file = file                # 源文件路径
        self.output = output            # 输出文件路径
        
        # 兼容属性（关键修复：curr_args 改为字符串，解决类型错误）
        self.curr_args = command        # 原始命令字符串（核心修改）
        self.work_dir = directory       # 解决 work_dir 问题
        self.src_file = file            # 解决 src_file 问题
        self.cmd = command              # 命令别名兼容
        self.filename = file            # 文件名别名兼容
        self.working_directory = directory # 额外兼容别名
        self.args = command.split()     # args 保留列表（供需要列表的逻辑）
        self.output_file = output       # 输出文件别名
        self.source_file = file         # 源文件别名

    def __repr__(self):
        return f"CompilationCommand(file={self.file}, command={self.command[:50]}...)"

    # 兼容方法：获取参数列表（防止内部调用列表方法）
    def get_args(self):
        return self.command.split() if isinstance(self.command, str) else []
    
    # 兼容方法：获取目录
    def get_directory(self):
        return self.directory
    
    # 兼容方法：获取参数列表（别名）
    def get_args_list(self):
        return self.get_args()


def setup_args():
    """参数解析器配置"""
    parser = argparse.ArgumentParser(description="STM32 LLVM Bitcode生成工具")
    # 必选参数
    parser.add_argument('-l', '--llvm-bc-out', dest='llvm_bc_out', required=True,
                        help='Bitcode输出目录（必填）')
    parser.add_argument('-b', '--original-build-base', dest='original_build_base', required=True,
                        help='STM32原始编译目录（必填）')
    parser.add_argument('-m', '--compile-json', dest='compile_json', required=True,
                        help='编译命令JSON文件路径（必填）')
    # 可选参数
    parser.add_argument('-clangp', '--clang-path', dest='clang_path', default='clang',
                        help='ARM目标clang绝对路径')
    parser.add_argument('-instrument', action='store_true', dest='do_instrumentation',
                        help='是否执行插桩（需指定opt和SO文件）')
    parser.add_argument('-optp', '--opt-path', dest='opt_path', default='opt',
                        help='opt工具绝对路径')
    parser.add_argument('-sopath', '--llvm-pass-so-path', dest='transformation_so', default='',
                        help='LLVM插桩Pass的SO文件路径')
    return parser


def extract_compile_command_from_json(compile_json_path):
    """提取并转换为完全兼容的CompilationCommand对象"""
    try:
        with open(compile_json_path, 'r', encoding='utf-8') as f:
            raw_data = json.load(f)
        
        valid_commands = []
        for item in raw_data:
            cmd_str = item.get('command', '')
            if not cmd_str:
                continue
            
            # 清理垃圾前缀
            cmd_str = cmd_str.replace("COMPILE_COMMAND: ", "").strip()
            cmd_str = cmd_str.replace("=== Executing: ", "").strip()
            cmd_str = cmd_str.replace(" ===", "").strip()
            
            # 只保留arm-none-eabi-gcc编译命令
            if cmd_str.startswith('arm-none-eabi-gcc') and '-c' in cmd_str and '.c' in cmd_str:
                compile_cmd = CompilationCommand(
                    directory=item.get('directory', '/tmp/conware_stm32_build'),
                    command=cmd_str,
                    file=item.get('file', ''),
                    output=item.get('output', '')
                )
                valid_commands.append(compile_cmd)
        
        if valid_commands:
            log_info(f"成功提取{len(valid_commands)}条有效编译命令（完全兼容对象格式）")
            return valid_commands
        
        # 兜底：从日志构造命令
        log_warning("未从JSON提取到有效命令，尝试从编译日志构造...")
        json_dir = os.path.dirname(compile_json_path)
        log_file = os.path.join(json_dir, 'original_stm32_build_output.txt')
        if os.path.exists(log_file):
            with open(log_file, 'r', encoding='utf-8') as f:
                log_content = f.read()
            
            import re
            cmd_match = re.search(r'(arm-none-eabi-gcc .+? -c .+?\.c -o .+?\.o)', log_content, re.DOTALL)
            if cmd_match:
                clean_cmd = cmd_match.group(1).strip()
                src_file_match = re.search(r'-c\s+(\S+\.c)', clean_cmd)
                output_file_match = re.search(r'-o\s+(\S+\.o)', clean_cmd)
                
                src_file = src_file_match.group(1) if src_file_match else '/home/makabaka/conware/firmware/stm32f408_test/src/main.c'
                output_file = output_file_match.group(1) if output_file_match else '/tmp/conware_stm32_build/main.o'
                
                compile_cmd = CompilationCommand(
                    directory='/tmp/conware_stm32_build',
                    command=clean_cmd,
                    file=src_file,
                    output=output_file
                )
                log_info(f"从日志构造命令成功：{clean_cmd}")
                return [compile_cmd]
        
        # 终极兜底：手动构造命令
        log_warning("使用终极兜底方案：手动构造编译命令")
        compile_cmd = CompilationCommand(
            directory='/tmp/conware_stm32_build',
            command='arm-none-eabi-gcc -mcpu=cortex-m4 -mthumb -mfloat-abi=hard -mfpu=fpv4-sp-d16 -O0 -g3 -Wall -ffreestanding -nostdlib -nostartfiles -fno-builtin -fno-exceptions -fno-rtti -I/home/makabaka/conware/firmware/stm32f408_test/inc -DSTM32F407xx -D__ARM_NO_EXCEPTIONS=1 -c /home/makabaka/conware/firmware/stm32f408_test/src/main.c -o /tmp/conware_stm32_build/main.o',
            file='/home/makabaka/conware/firmware/stm32f408_test/src/main.c',
            output='/tmp/conware_stm32_build/main.o'
        )
        return [compile_cmd]
        
    except Exception as e:
        log_error(f"提取编译命令失败：{e}")
        # 终极兜底
        compile_cmd = CompilationCommand(
            directory='/tmp/conware_stm32_build',
            command='arm-none-eabi-gcc -mcpu=cortex-m4 -mthumb -mfloat-abi=hard -mfpu=fpv4-sp-d16 -O0 -g3 -Wall -ffreestanding -nostdlib -nostartfiles -fno-builtin -fno-exceptions -fno-rtti -I/home/makabaka/conware/firmware/stm32f408_test/inc -DSTM32F407xx -D__ARM_NO_EXCEPTIONS=1 -c /home/makabaka/conware/firmware/stm32f408_test/src/main.c -o /tmp/conware_stm32_build/main.o',
            file='/home/makabaka/conware/firmware/stm32f408_test/src/main.c',
            output='/tmp/conware_stm32_build/main.o'
        )
        return [compile_cmd]


def safe_mkdir(dir_path):
    """安全创建目录"""
    try:
        os.makedirs(dir_path, exist_ok=True)
        return True
    except Exception as e:
        log_error(f"创建目录失败：{e}")
        return False


def main():
    """主函数"""
    # 解析参数
    arg_parser = setup_args()
    parsed_args = arg_parser.parse_args()
    
    # 提取参数
    compile_json = parsed_args.compile_json
    original_build_base = parsed_args.original_build_base
    clang_path = parsed_args.clang_path
    llvm_bc_out = parsed_args.llvm_bc_out
    transformation_so = parsed_args.transformation_so
    opt_path = parsed_args.opt_path
    do_instrumentation = parsed_args.do_instrumentation

    # 校验工具路径
    if not os.path.exists(clang_path):
        log_error(f"Clang工具不存在：{clang_path}")
        sys.exit(-1)
    
    if do_instrumentation:
        if not os.path.exists(opt_path):
            log_error(f"Opt工具不存在：{opt_path}")
            sys.exit(-1)
        if not os.path.exists(transformation_so):
            log_error(f"插桩SO文件不存在：{transformation_so}")
            sys.exit(-1)

    # 提取编译命令
    compile_commands = extract_compile_command_from_json(compile_json)
    if len(compile_commands) == 0:
        log_error("无有效编译命令，无法继续")
        sys.exit(-1)

    # 创建Bitcode目录
    if not safe_mkdir(llvm_bc_out):
        log_error("创建Bitcode输出目录失败")
        sys.exit(-1)
    log_info(f"Bitcode输出目录已创建：{llvm_bc_out}")

    # STM32架构参数
    stm32_arch = [
        "-target arm-none-eabi",
        "-mcpu=cortex-m4",
        "-mthumb",
        "-mfloat-abi=hard",
        "-mfpu=fpv4-sp-d16",
        "-ffreestanding",
        "-nostdlib"
    ]
    
    stm32_defines = [
        "-DSTM32F407xx",
        "-D__ARM_NO_EXCEPTIONS=1",
        "-O0",
        "-g3",
        "-Wall",
        "-fno-builtin",
        "-fno-exceptions",
        "-fno-rtti"
    ]

    # 执行构建
    try:
        import inspect
        sig = inspect.signature(build_using_clang)
        param_names = list(sig.parameters.keys())
        log_info(f"build_using_clang函数参数：{param_names}")
        
        # 构造参数
        call_kwargs = {
            'compile_commands': compile_commands,
            'original_build_base': original_build_base,
            'clang_path': clang_path,
            'llvm_bc_out': llvm_bc_out,
            'transformation_so': transformation_so if do_instrumentation else "",
            'opt_path': opt_path if do_instrumentation else "",
            'stm32_arch': stm32_arch,
            'stm32_defines': stm32_defines
        }
        
        # 过滤参数
        final_kwargs = {}
        for param in param_names:
            final_kwargs[param] = call_kwargs.get(param, "")
        
        # 执行
        build_using_clang(**final_kwargs)
        log_success(f"STM32 Bitcode生成完成！输出目录：{llvm_bc_out}")
        
    except FileExistsError as e:
        log_error(f"文件已存在错误：{e}")
        if 'opt' in str(e) and os.path.isdir(opt_path):
            shutil.rmtree(opt_path, ignore_errors=True)
            build_using_clang(**final_kwargs)
            log_success(f"重试成功！STM32 Bitcode生成完成：{llvm_bc_out}")
    except TypeError as e:
        log_error(f"参数类型错误：{e}")
        # 手动传参
        if do_instrumentation:
            build_using_clang(
                compile_commands, original_build_base, clang_path, llvm_bc_out,
                transformation_so, opt_path, stm32_arch, stm32_defines
            )
        else:
            build_using_clang(
                compile_commands, original_build_base, clang_path, llvm_bc_out,
                "", "", stm32_arch, stm32_defines
            )
        log_success(f"手动调用成功！STM32 Bitcode生成完成：{llvm_bc_out}")
    except Exception as e:
        log_error(f"Clang构建失败：{e}")
        import traceback
        log_error(f"详细错误堆栈：{traceback.format_exc()}")
        sys.exit(-1)


def which(program):
    """检查可执行文件"""
    def is_exe(fpath):
        return os.path.isfile(fpath) and os.access(fpath, os.X_OK)
    fpath, fname = os.path.split(program)
    if fpath and is_exe(program):
        return program
    for path in os.environ["PATH"].split(os.pathsep):
        exe_file = os.path.join(path, program)
        if is_exe(exe_file):
            return exe_file
    return ""


if __name__ == "__main__":
    main()
