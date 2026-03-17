import os
import json
from multiprocessing import Pool
from typing import List, Tuple, Dict, Optional, Any
from log_stuff import log_info, log_success, log_error  # 假设log_stuff提供这些日志函数

# ===================== 配置常量 =====================
# LLVM 目标优化标志
TARGET_OPTIMIZATION_FLAGS = ['-O0']
# LLVM 调试信息标志
DEBUG_INFO_FLAGS = ['-g']
# 架构目标关键字
ARCH_TARGET = '-target'
# ARM 32位 LLVM 架构标识
ARM_32_LLVM_ARCH = 'armv7'
# 禁用 LLVM 警告的标志
DISABLE_WARNINGS = ['-Wno-return-type', '-w', '-fshort-enums']
# 默认 Clang 二进制路径
CLANG_PATH = 'clang'
# 生成 LLVM 位码的标志
EMIT_LLVM_FLAG = '-emit-llvm'


# ===================== 工具函数 =====================
def _run_program(args: Tuple[str, str]) -> None:
    """
    在指定工作目录运行编译命令
    :param args: 元组(工作目录, 要执行的命令)
    :return: None
    """
    workdir, cmd_to_run = args  # 修复Python3元组解包问题
    curr_dir = os.getcwd()
    try:
        os.chdir(workdir)
        log_info(f"执行命令: {cmd_to_run} (工作目录: {workdir})")
        os.system(cmd_to_run)
    except Exception as e:
        log_error(f"执行命令失败: {cmd_to_run}, 错误: {str(e)}")
    finally:
        os.chdir(curr_dir)  # 确保切回原目录


def _is_allowed_flag(curr_flag: str) -> bool:
    """
    检查GCC标志是否允许在LLVM命令行中使用
    :param curr_flag: 待检查的编译标志
    :return: 允许返回True，否则False
    """
    # 过滤优化标志（保留原逻辑，可根据需要启用）
    # if curr_flag.startswith("-O"):
    #     return False
    return True


def _get_clang_build_str(
        clang_path: str,
        build_args: List[str],
        src_build_dir: str,
        work_dir: str,
        src_file_path: str,
        output_file_path: str,
        llvm_bit_code_out: str
) -> Tuple[str, str, str, str, str, str, str]:
    """
    将GCC编译命令转换为Clang命令，生成LLVM位码和目标文件相关命令
    :param clang_path: Clang二进制路径
    :param build_args: 原始编译器参数
    :param src_build_dir: Arduino构建器的原始构建目录
    :param work_dir: 原始命令运行目录
    :param src_file_path: 待编译的源文件路径
    :param output_file_path: 原始目标文件路径
    :param llvm_bit_code_out: LLVM位码输出目录
    :return: (工作目录, 原始目标文件, 目标位码文件, 位码转目标文件模板命令,
             生成位码的命令, 生成LLVM目标文件的命令, 从位码生成目标文件的命令)
    """
    modified_build_args = [clang_path, EMIT_LLVM_FLAG]
    # 添加架构目标
    modified_build_args.extend([ARCH_TARGET, ARM_32_LLVM_ARCH])
    # 添加调试和优化标志
    modified_build_args.extend(DEBUG_INFO_FLAGS)
    modified_build_args.extend(TARGET_OPTIMIZATION_FLAGS)
    # 添加禁用警告标志
    modified_build_args.extend(DISABLE_WARNINGS)

    # 计算相对目标文件路径，构建位码输出目录
    rel_obj_file = output_file_path.split(src_build_dir)[-1].lstrip('/')
    target_out_dir = os.path.join(llvm_bit_code_out, os.path.dirname(rel_obj_file))
    os.makedirs(target_out_dir, exist_ok=True)  # 简化目录创建（Python3.2+支持）
    target_bc_file = os.path.join(target_out_dir, f"{os.path.basename(output_file_path)}.bc")

    # 过滤允许的编译参数
    for curr_op in build_args:
        if _is_allowed_flag(curr_op):
            modified_build_args.append(curr_op)

    # 构建从位码生成目标文件的参数（移除emit-llvm）
    to_obj_from_bc_build_args = modified_build_args.copy()
    to_obj_from_bc_build_args.remove(EMIT_LLVM_FLAG)
    bitcode_to_obj_file_template = to_obj_from_bc_build_args.copy()

    # 构建生成位码的命令
    modified_build_args.extend(["-c", src_file_path, "-o", target_bc_file])
    # 构建直接生成LLVM目标文件的命令
    to_obj_file_build_args = modified_build_args.copy()
    to_obj_file_build_args.remove(EMIT_LLVM_FLAG)
    to_obj_file_build_args.append(f"{target_bc_file[:-3]}.llvm.obj")  # 修复后缀截取（.bc → 空）
    # 构建从位码生成目标文件的命令
    to_obj_from_bc_build_args.extend(["-c", target_bc_file, "-o", f"{target_bc_file}_frombc.obj"])

    return (
        work_dir, output_file_path, target_bc_file,
        ' '.join(bitcode_to_obj_file_template),
        ' '.join(modified_build_args),
        ' '.join(to_obj_file_build_args),
        ' '.join(to_obj_from_bc_build_args)
    )


def build_using_clang(
        compile_commands: List[Any],  # 假设compile_commands是包含编译命令对象的列表
        original_build_base: str,
        clang_path: str = CLANG_PATH,
        llvm_bc_out: str = "./llvm_bc_out",
        transformation_so: Optional[str] = None,
        opt_path: Optional[str] = None
) -> None:
    """
    使用Clang编译代码并生成LLVM位码，可选执行LLVM变换并转换回目标文件
    :param compile_commands: 编译命令列表（包含src_file/output_file/work_dir/curr_args等属性）
    :param original_build_base: 原始构建基础目录
    :param clang_path: Clang二进制路径
    :param llvm_bc_out: LLVM位码输出目录
    :param transformation_so: LLVM变换插件(.so)路径
    :param opt_path: LLVM opt工具路径
    :return: None
    """
    # 创建输出目录
    os.makedirs(llvm_bc_out, exist_ok=True)
    # 定义输出文件路径
    output_llvm_sh_file = os.path.join(llvm_bc_out, 'clang_build.json')
    human_llvm_txt_file = os.path.join(llvm_bc_out, 'clang_build.txt')

    log_info(f"将编译命令写入JSON文件: {output_llvm_sh_file}")
    log_info(f"将可读格式编译命令写入TXT文件: {human_llvm_txt_file}")

    all_compilation_commands: List[Tuple[str, str]] = []
    target_output_commands: List[Dict[str, str]] = []
    transformation_info: Dict[str, Tuple[str, str]] = {}

    # 处理每个编译命令
    for idx, curr_compilation_command in enumerate(compile_commands):
        try:
            (work_dir, orig_output, target_bc_file,
             bitcode_to_obj_file_template, target_command_bc_cmd,
             target_obj_cmd, target_bc_to_obj_cmd) = _get_clang_build_str(
                clang_path, curr_compilation_command.curr_args,
                original_build_base, curr_compilation_command.work_dir,
                curr_compilation_command.src_file,
                curr_compilation_command.output_file,
                llvm_bc_out
            )
        except Exception as e:
            log_error(f"处理第{idx}个编译命令失败: {str(e)}，跳过该命令")
            continue

        all_compilation_commands.append((work_dir, target_command_bc_cmd))
        # 构建命令字典
        cmd_dict = {
            "orig_obj_file": orig_output,
            "to_llvm_bc": target_command_bc_cmd,
            "to_llvm_obj": target_obj_cmd,
            "from_llvm_bc_to_obj": target_bc_to_obj_cmd
        }
        target_output_commands.append(cmd_dict)
        transformation_info[orig_output] = (target_bc_file, bitcode_to_obj_file_template)

    # 写入可读格式的TXT文件
    with open(human_llvm_txt_file, 'w', encoding='utf-8') as fp_human_out:
        fp_human_out.write(json.dumps(target_output_commands, indent=4, ensure_ascii=False))

    # 写入JSON文件（修复原格式错误）
    with open(output_llvm_sh_file, 'w', encoding='utf-8') as fp_out:
        json.dump(target_output_commands, fp_out, indent=4, sort_keys=True, ensure_ascii=False)

    # 多进程执行编译命令
    if all_compilation_commands:
        log_info(f"共获取{len(all_compilation_commands)}个编译命令，启动多进程执行")
        with Pool() as p:  # 使用上下文管理器自动释放Pool资源
            p.map(_run_program, all_compilation_commands)
        log_info("多进程编译命令执行完成")
    else:
        log_info("无编译命令需要执行，跳过多进程步骤")

    # 执行LLVM变换（如果指定了插件和opt路径）
    if transformation_so and opt_path:
        log_info("开始执行LLVM变换并转换回目标文件")
        for curr_output_obj in transformation_info.keys():
            orig_bc_file, bitcode_to_obj_template = transformation_info[curr_output_obj]
            if not os.path.exists(orig_bc_file):
                log_error(f"位码文件不存在: {orig_bc_file}，跳过变换")
                continue

            # 检查位码文件有效性
            try:
                with open(orig_bc_file, 'rb') as fp:  # 二进制模式读取
                    header = fp.read(2)
                    if header != b"BC":  # 位码文件魔数是BC（二进制）
                        log_error(f"位码文件无效: {orig_bc_file}，直接复制原文件")
                        os.system(f"cp {orig_bc_file} {curr_output_obj}")
                        continue

                # 执行变换命令
                transformation_bc_file = f"{orig_bc_file}.transform.bc"
                transformation_command = (
                    f"{opt_path} -load {transformation_so} -logmmio "
                    f"{orig_bc_file} -o {transformation_bc_file}"
                )
                log_info(f"执行变换命令: {transformation_command}")
                os.system(transformation_command)

                # 从变换后的位码生成目标文件
                bc_to_obj_cmd = (
                    f"{bitcode_to_obj_template} -c {transformation_bc_file} "
                    f"-o {curr_output_obj}"
                )
                log_info(f"位码转目标文件: {bc_to_obj_cmd}")
                os.system(bc_to_obj_cmd)
            except Exception as e:
                log_error(f"处理变换文件{orig_bc_file}失败: {str(e)}")
        log_success("LLVM变换执行完成")
    else:
        log_info("未指定变换插件或opt路径，跳过LLVM变换步骤")


# 示例调用（可选，用于测试）
if __name__ == "__main__":
    # 模拟编译命令对象（根据实际场景调整）
    class MockCompileCommand:
        def __init__(self, curr_args, work_dir, src_file, output_file):
            self.curr_args = curr_args
            self.work_dir = work_dir
            self.src_file = src_file
            self.output_file = output_file

    # 构建模拟编译命令列表
    mock_commands = [
        MockCompileCommand(
            curr_args=["-x", "c", "-Wall"],
            work_dir="./src",
            src_file="./src/test.c",
            output_file="./build/test.o"
        )
    ]

    # 调用构建函数
    build_using_clang(
        compile_commands=mock_commands,
        original_build_base="./build",
        clang_path="clang",
        llvm_bc_out="./llvm_bc_out",
        # transformation_so="./transform.so",  # 实际使用时取消注释
        # opt_path="opt"  # 实际使用时取消注释
    )
