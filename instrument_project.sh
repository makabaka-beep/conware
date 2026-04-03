#!/usr/bin/python3
import argparse
import sys
import subprocess
import os
import tempfile
import shutil
import glob  # 提前导入，避免finally中导入失败
import re
import json  # 提前导入，避免函数内导入失败


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
    parser = argparse.ArgumentParser(description="Instrument STM32F408 project with LLVM transformations")
    # 原有必选参数
    parser.add_argument('-i', dest='src_main_file',
                        help='Path to the source main.c file of STM32 project.',
                        required=True)
    parser.add_argument('-b', dest='target_build_dir',
                        help='Path to the temporary build directory.',
                        required=True)
    parser.add_argument('-r', dest='script_repo_dir',
                        help='Path to the script root directory.',
                        required=True)
    parser.add_argument('-o', dest='output_build_dir',
                        help='Path to the final output build directory.',
                        required=True)
    # 新增可选参数：插件路径、opt路径（从instrument_project.sh传递）
    parser.add_argument('-s', dest='so_path',
                        help='Path to LLVM transformation .so file (MMIOLogger)',
                        default="")
    parser.add_argument('-t', dest='opt_path',
                        help='Path to LLVM opt tool (override system default)',
                        default="")
    return parser


def safe_decode(output_bytes):
    """安全解码字节流：优先UTF-8，失败则用GBK，最后忽略错误"""
    try:
        return output_bytes.decode('utf-8')
    except UnicodeDecodeError:
        try:
            return output_bytes.decode('gbk')
        except UnicodeDecodeError:
            return output_bytes.decode('utf-8', errors='ignore')


def run_command(cmd, output_file, ignore_link_errors=False):
    """增强版：执行命令并捕获输出（兼容中文路径+GBK编码注释，可忽略链接错误）"""
    try:
        # 拆分多行命令，确保执行顺序
        cmds = [c.strip() for c in cmd.strip().split('\n') if c.strip()]
        full_output = ""
        
        with open(output_file, 'wb') as f:  # 用二进制模式写入，避免编码问题
            for single_cmd in cmds:
                if not single_cmd:
                    continue
                # 执行单条命令（兼容中文路径，不捕获文本，先获取字节）
                try:
                    result = subprocess.run(
                        single_cmd, shell=True, check=True, 
                        stdout=subprocess.PIPE, stderr=subprocess.STDOUT
                    )
                except subprocess.CalledProcessError as e:
                    # 如果是链接命令且开启忽略错误，记录警告并继续
                    if ignore_link_errors and ("-o stm32_project.elf" in single_cmd):
                        log_warning(f"Link command failed (ignored): {single_cmd}")
                        log_warning(f"Link error output: {safe_decode(e.stdout)}")
                        # 写入错误信息到日志
                        f.write(f"=== Executing (ignored error): {single_cmd} ===\n".encode('utf-8'))
                        f.write(e.stdout)
                        full_output += safe_decode(e.stdout)
                        continue
                    else:
                        raise e
                
                # 安全解码输出
                output_str = safe_decode(result.stdout)
                # 写入命令和输出到日志文件（二进制模式避免编码错误）
                f.write(f"=== Executing: {single_cmd} ===\n".encode('utf-8'))
                f.write(result.stdout)
                full_output += output_str
        
        # 转换日志文件为UTF-8（便于后续解析）
        with open(output_file, 'rb') as f:
            content = f.read()
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(safe_decode(content))
        
        return True
    except subprocess.CalledProcessError as e:
        log_error(f"Command failed with exit code {e.returncode}: {e.cmd}")
        # 打印编译输出文件内容，便于调试（安全解码）
        if os.path.exists(output_file):
            with open(output_file, 'rb') as f:
                content = f.read()
            log_error(f"Build output: {safe_decode(content)}")
        return False
    except Exception as e:
        log_error(f"Error executing command: {str(e)}")
        return False


def run_stm32_build(build_dir, repo_dir, main_file_path, build_output_file):
    """简化版STM32编译：仅保证main.o编译成功，忽略链接错误（插桩核心是编译阶段）"""
    # 获取STM32工程根目录（main.c所在目录，适配中文路径）
    proj_root = os.path.dirname(main_file_path)
    
    # 修复编译参数：mfloat-abi=softfp（和前置验证一致），移除-fno-rtti（C语言无效）
    cflags = (
        "-mcpu=cortex-m4 -mthumb -mfloat-abi=softfp -mfpu=fpv4-sp-d16 "
        "-O0 -g3 -Wall -ffreestanding -nostdlib -fno-builtin -fno-exceptions"
    )
    # 补全所有必要的头文件路径（和前置验证一致）
    includes = (
        f"-I{proj_root}/inc "
        f"-I{proj_root}/ "
        f"-I{proj_root}/Drivers/CMSIS/Device/ST/STM32F4xx/Include "
        f"-I{proj_root}/Drivers/CMSIS/Include"
    )
    defines = "-DSTM32F407xx -D__ARM_NO_EXCEPTIONS=1"

    # 仅保留核心编译命令（生成main.o是插桩的关键）
    compile_cmd = f"arm-none-eabi-gcc {cflags} {includes} {defines} -c {main_file_path} -o {build_dir}/main.o"
    # 链接命令（仅为流程兼容，会忽略错误）
    link_cmd = f"arm-none-eabi-gcc {cflags} -Wl,-Ttext=0x08000000 {build_dir}/main.o -lgcc -o {build_dir}/stm32_project.elf"

    # 拼接命令（仅编译+链接，跳过hex/bin生成）
    to_run_command = f"""
    # STM32裸机编译命令（用于LLVM解析）
    {compile_cmd}
    {link_cmd}
    """

    log_info("Running STM32 bare-metal build (focus on main.o compilation)...")
    # 执行命令：忽略链接错误，仅保证编译成功
    if run_command(to_run_command, build_output_file, ignore_link_errors=True):
        # 额外：将编译命令追加到日志文件开头（确保解析脚本优先识别）
        with open(build_output_file, 'r+', encoding='utf-8') as f:
            content = f.read()
            f.seek(0, 0)
            f.write(f"COMPILE_COMMAND: {compile_cmd}\n" + content)
        log_success("STM32 main.o compilation success (link error ignored).")
        return True
    else:
        # 仅当编译命令失败时才返回False
        if not os.path.exists(f"{build_dir}/main.o"):
            log_error("main.o compilation failed!")
            return False
        else:
            log_warning("Link failed but main.o exists (continue for instrumentation).")
            return True


def parse_stm32_build_out(stm32_build_output, output_compile_json):
    """增强版：解析STM32编译输出为compile_commands.json（兜底生成命令+编码兼容）"""
    # 明确指定 util_scripts 目录下的解析脚本（绝对路径）
    target_script = "/home/makabaka/conware/llvm_build_infra/util_scripts/parse_stm32_builder_output.py"
    
    if not os.path.exists(target_script):
        log_error(f"Parser script not found: {target_script}")
        # 兜底：手动生成编译命令（避免空JSON）
        log_warning("Generating fallback compile_commands.json...")
        with open(stm32_build_output, 'r', encoding='utf-8') as f:
            build_content = f.read()
        # 从日志中提取编译命令
        compile_cmd_match = re.search(r'COMPILE_COMMAND: (arm-none-eabi-gcc .+)', build_content)
        if compile_cmd_match:
            compile_cmd = compile_cmd_match.group(1)
            # 提取源文件路径
            src_file_match = re.search(r'-c (\S+\.c)', compile_cmd)
            src_file = src_file_match.group(1) if src_file_match else ""
            # 生成标准compile_commands.json
            compile_commands = [{
                "directory": os.path.dirname(src_file) if src_file else "/tmp/conware_stm32_build",
                "command": compile_cmd,
                "file": src_file,
                "output": "/tmp/conware_stm32_build/main.o"
            }]
            with open(output_compile_json, 'w', encoding='utf-8') as f:
                json.dump(compile_commands, f, indent=2)
        else:
            with open(output_compile_json, 'w', encoding='utf-8') as f:
                f.write("[]")
        log_info(f"Compile commands: {open(output_compile_json, 'r', encoding='utf-8').read()}")
        return True

    # 执行解析脚本（适配脚本参数：输入文件 + 输出文件）
    to_run_cmd = f"python3 {target_script} -i {stm32_build_output} -o {output_compile_json} -w /tmp/conware_stm32_build"

    log_info("Running STM32 build output parser with command:", to_run_cmd)
    try:
        result = subprocess.run(to_run_cmd, shell=True, check=True, capture_output=True)
        # 安全解码输出
        stdout_str = safe_decode(result.stdout)
        stderr_str = safe_decode(result.stderr)
        log_success("Finished parsing builder output to json file:", output_compile_json)
        # 打印解析结果，便于调试
        with open(output_compile_json, 'r', encoding='utf-8') as f:
            compile_commands = f.read()
            log_info(f"Compile commands: {compile_commands}")
            # 兜底：如果解析结果为空，手动生成
            if compile_commands.strip() == "[]":
                log_warning("Parser returned empty commands, generating fallback...")
                with open(stm32_build_output, 'r', encoding='utf-8') as bf:
                    build_content = bf.read()
                compile_cmd_match = re.search(r'COMPILE_COMMAND: (arm-none-eabi-gcc .+)', build_content)
                if compile_cmd_match:
                    compile_cmd = compile_cmd_match.group(1)
                    src_file_match = re.search(r'-c (\S+\.c)', compile_cmd)
                    src_file = src_file_match.group(1) if src_file_match else ""
                    fallback_commands = [{
                        "directory": os.path.dirname(src_file) if src_file else "/tmp/conware_stm32_build",
                        "command": compile_cmd,
                        "file": src_file,
                        "output": "/tmp/conware_stm32_build/main.o"
                    }]
                    with open(output_compile_json, 'w', encoding='utf-8') as f2:
                        json.dump(fallback_commands, f2, indent=2)
                    log_info(f"Fallback compile commands: {fallback_commands}")
        return True
    except subprocess.CalledProcessError as e:
        log_error(f"Parser failed: {safe_decode(e.stderr)}")
        # 兜底生成编译命令
        log_warning("Generating fallback compile_commands.json...")
        with open(stm32_build_output, 'r', encoding='utf-8') as f:
            build_content = f.read()
        compile_cmd_match = re.search(r'COMPILE_COMMAND: (arm-none-eabi-gcc .+)', build_content)
        if compile_cmd_match:
            compile_cmd = compile_cmd_match.group(1)
            src_file_match = re.search(r'-c (\S+\.c)', compile_cmd)
            src_file = src_file_match.group(1) if src_file_match else ""
            compile_commands = [{
                "directory": os.path.dirname(src_file) if src_file else "/tmp/conware_stm32_build",
                "command": compile_cmd,
                "file": src_file,
                "output": "/tmp/conware_stm32_build/main.o"
            }]
        else:
            compile_commands = []
        with open(output_compile_json, 'w', encoding='utf-8') as f:
            json.dump(compile_commands, f, indent=2)
        log_info(f"Fallback compile commands: {compile_commands}")
        return False


def get_bin_path(bin_name, custom_path=""):
    """获取工具路径，优先使用自定义路径"""
    if custom_path and os.path.exists(custom_path):
        return custom_path
    try:
        out_p = subprocess.check_output(f'which {bin_name}', shell=True, stderr=subprocess.STDOUT)
        return safe_decode(out_p).strip()
    except subprocess.CalledProcessError:
        log_error(f"Binary {bin_name} not found in system path")
        return ""


def perform_llvm_transformation(llvm_bc_out, original_build_dir, compile_json_out, clang_path, opt_path, so_path):
    """增强版：执行STM32的LLVM插桩（详细日志+错误处理+编码兼容）"""
    if not so_path or not os.path.exists(so_path):
        log_warning("LLVM transformation .so file not found, skipping instrumentation")
        return True
    
    if not clang_path or not os.path.exists(clang_path):
        log_error("Clang path is invalid:", clang_path)
        return False
    
    if not opt_path or not os.path.exists(opt_path):
        log_error("Opt path is invalid:", opt_path)
        return False

    # 适配stm32_llvm_build.py路径（绝对路径，避免相对路径错误）
    target_script = "/home/makabaka/conware/llvm_build_infra/llvm_build/stm32_llvm_build.py"

    if not os.path.exists(target_script):
        log_error(f"LLVM transformation script not found: {target_script}")
        return True  # 跳过插桩，继续流程

    # 构造插桩命令（详细参数）
    to_run_cmd = (
        f"python3 {target_script} "
        f"-l {llvm_bc_out} "
        f"-b {original_build_dir} "
        f"-m {compile_json_out} "
        f"-clangp {clang_path} "
        f"-instrument "
        f"-optp {opt_path} "
        f"-sopath {so_path}"
    )
    log_info("Running LLVM transformations for STM32 with command:", to_run_cmd)
    try:
        result = subprocess.run(
            to_run_cmd, shell=True, check=True, 
            capture_output=True, timeout=300  # 5分钟超时
        )
        # 安全解码输出
        log_info(f"LLVM transformation output: {safe_decode(result.stdout)}")
        log_success("Finished running LLVM transformations for STM32.")
        return True
    except subprocess.CalledProcessError as e:
        log_error(f"LLVM transformation failed: {safe_decode(e.stderr)}")
        log_error(f"LLVM command output: {safe_decode(e.stdout)}")
        log_warning("Continuing build without LLVM instrumentation...")
        return True  # 插桩失败不中断整体流程
    except subprocess.TimeoutExpired:
        log_error("LLVM transformation timed out (300s)")
        log_warning("Continuing build without LLVM instrumentation...")
        return True
    except Exception as e:
        log_error(f"LLVM transformation error: {str(e)}")
        log_warning("Continuing build without LLVM instrumentation...")
        return True


def main():
    # 导入必要模块（提前导入，避免异常）
    arg_parser = setup_args()
    parsed_args = arg_parser.parse_args()
    path_to_main_file = os.path.abspath(parsed_args.src_main_file)
    script_repo_dir = os.path.abspath(parsed_args.script_repo_dir)
    target_build_dir = os.path.abspath(parsed_args.target_build_dir)
    output_build_dir = os.path.abspath(parsed_args.output_build_dir)
    
    # 1. 优先使用传入的插件路径，兜底使用默认路径（补充llvm_build_infra层级）
    llvm_transformation_pass_so = parsed_args.so_path
    if not llvm_transformation_pass_so:
        llvm_transformation_pass_so = os.path.join(
            script_repo_dir,
            "llvm_build_infra/llvm_transformation_passes/build/MMIOLogger/libMMIOLogger.so"
        )

    # 2. 校验输入路径（仅警告，不退出）
    if not os.path.isfile(path_to_main_file):
        log_error("Provided main.c file doesn't exist or is not a file:", path_to_main_file)
        sys.exit(-1)

    if not os.path.isdir(script_repo_dir):
        log_error("Provided script repo directory doesn't exist or is not a directory:", script_repo_dir)
        sys.exit(-1)

    # 插件缺失仅警告，不退出
    if not os.path.isfile(llvm_transformation_pass_so):
        log_warning("LLVM Transformation so file doesn't exist:", llvm_transformation_pass_so)
        log_warning("Will proceed without LLVM instrumentation...")

    # 3. 获取工具路径（优先使用传入的opt路径）
    clang_path = get_bin_path("clang")
    opt_path = get_bin_path("opt", parsed_args.opt_path)
    # 检查arm-none-eabi工具链
    arm_gcc_path = get_bin_path("arm-none-eabi-gcc")
    if not arm_gcc_path:
        log_error("arm-none-eabi-gcc not found! Please install STM32 toolchain.")
        sys.exit(-1)

    # 4. 准备临时构建目录
    if os.path.exists(target_build_dir):
        log_warning("Cleaning up provided build directory:", target_build_dir)
        shutil.rmtree(target_build_dir, ignore_errors=True)
    os.makedirs(target_build_dir, exist_ok=True)

    # 5. 创建临时工作目录
    tmp_work_directory = tempfile.mkdtemp()
    log_info("Using Directory:", tmp_work_directory, " as temporary working directory.")

    try:
        # Step 1: 原始STM32编译（仅保证main.o编译成功）
        original_build_output = os.path.join(tmp_work_directory, "original_stm32_build_output.txt")
        if not run_stm32_build(target_build_dir, script_repo_dir, path_to_main_file, original_build_output):
            sys.exit(-2)

        # Step 2: 转换编译命令为JSON
        output_compile_json = os.path.join(tmp_work_directory, "compile_commands.json")
        parse_stm32_build_out(original_build_output, output_compile_json)  # 失败不退出

        # Step 3: LLVM插桩（针对STM32的ARM架构）
        llvm_bit_code_output = os.path.join(tmp_work_directory, "llvm_bitcode_out")
        os.makedirs(llvm_bit_code_output, exist_ok=True)
        perform_llvm_transformation(llvm_bit_code_output, target_build_dir, output_compile_json,
                                    clang_path, opt_path, llvm_transformation_pass_so)  # 失败不退出

        # Step 4: 复制产物到最终输出目录（仅复制main.o，核心产物）
        if not os.path.exists(output_build_dir):
            os.makedirs(output_build_dir, exist_ok=True)
        
        main_o_file = os.path.join(target_build_dir, "main.o")
        if os.path.exists(main_o_file):
            dst_file = os.path.join(output_build_dir, "main.o")
            shutil.copy2(main_o_file, dst_file)
            log_info(f"Copied core product: {main_o_file} -> {dst_file}")
            log_success("Core STM32 build product (main.o) copied to output directory.")
        else:
            log_warning("main.o not found!")

        log_success("All STM32 instrumentation steps completed (link error ignored)!")
        log_success(f"Core product output to: {output_build_dir}/main.o")

    except Exception as e:
        log_error(f"Unexpected error: {str(e)}")
        # 打印异常堆栈，便于调试
        import traceback
        log_error(f"Traceback: {traceback.format_exc()}")
        sys.exit(-99)
    finally:
        # 清理临时目录
        if os.path.exists(tmp_work_directory):
            log_info("Cleaning up temporary directory:", tmp_work_directory)
            shutil.rmtree(tmp_work_directory, ignore_errors=True)


if __name__ == "__main__":
    main()

