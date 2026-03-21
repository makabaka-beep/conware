import os
import json
from multiprocessing import Pool
from typing import List, Tuple, Dict, Optional, Any
from log_stuff import log_info, log_success, log_error  # 假设log_stuff提供这些日志函数

# ===================== 配置常量（适配STM32） =====================
# STM32 常用优化级别（根据实际需求调整）
TARGET_OPTIMIZATION_FLAGS = ['-O2']
# LLVM 调试信息标志（保留DWARF格式适配STM32调试）
DEBUG_INFO_FLAGS = ['-g', '-gdwarf-4']
# 架构目标关键字
ARCH_TARGET = '-target'
# STM32 主流ARM架构标识（ARM Cortex-M系列，如M4/M7用armv7e-m，M0/M0+用armv6-m）
# 根据实际芯片调整：armv6-m(M0/M0+)、armv7-m(M3)、armv7e-m(M4/M7)、armv8-m.main(M33)
STM32_LLVM_ARCH = 'armv7e-m'
# STM32 编译必备参数：指定浮点ABI（M4/M7带FPU用hard，无FPU用soft/softfp）
FLOAT_ABI_FLAGS = ['-mfloat-abi=hard', '-mfpu=fpv4-sp-d16']
# 禁用 LLVM 警告的标志
DISABLE_WARNINGS = ['-Wno-return-type', '-w', '-fshort-enums']
# 默认 Clang 二进制路径（建议指定完整路径，如armclang）
CLANG_PATH = 'clang'
# 生成 LLVM 位码的标志
EMIT_LLVM_FLAG = '-emit-llvm'
# STM32 编译必备：指定MCU型号、芯片定义（根据实际型号调整）
STM32_DEFINES = [
    '-DSTM32F407xx',  # 替换为实际MCU型号，如STM32F103xx、STM32L476xx等
    '-DUSE_HAL_DRIVER',  # 使用HAL库时添加
    '-DHSE_VALUE=8000000'  # 外部晶振频率，根据硬件调整
]
# STM32 链接脚本/编译模式相关
STM32_COMPILE_FLAGS = [
    '-mthumb',  # 强制THUMB模式（STM32必选）
    '-ffunction-sections', '-fdata-sections',  # 段分离，优化链接
    '-fno-exceptions', '-fno-rtti',  # 关闭异常和RTTI，适配嵌入式
    '-std=gnu11'  # STM32常用C标准
]


# ===================== 工具函数 =====================
def _run_program(args: Tuple[str, str]) -> None:
    """
    在指定工作目录运行编译命令
    :param args: 元组(工作目录, 要执行的命令)
    :return: None
    """
    workdir, cmd_to_run = args
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
    检查GCC/ARMCC标志是否允许在LLVM命令行中使用（适配STM32）
    :param curr_flag: 待检查的编译标志
    :return: 允许返回True，否则False
    """
    # 过滤STM32不兼容的标志
    disallowed_flags = [
        '-mcpu=cortex-m4',  # 替换为LLVM格式的架构指定
        '-mcpu=cortex-m7',
        '-march=armv7e-m',
        '--specs=nano.specs',  # 需特殊处理newlib-nano
        '--specs=nosys.specs'
    ]
    if curr_flag in disallowed_flags:
        return False
    # 保留优化标志（STM32需要O0/O2等）
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
    将STM32的GCC/ARMCC编译命令转换为Clang命令，生成LLVM位码和目标文件相关命令
    :param clang_path: Clang二进制路径
    :param build_args: 原始编译器参数
    :param src_build_dir: STM32构建器的原始构建目录
    :param work_dir: 原始命令运行目录
    :param src_file_path: 待编译的源文件路径
    :param output_file_path: 原始目标文件路径
    :param llvm_bit_code_out: LLVM位码输出目录
    :return: (工作目录, 原始目标文件, 目标位码文件, 位码转目标文件模板命令,
             生成位码的命令, 生成LLVM目标文件的命令, 从位码生成目标文件的命令)
    """
    modified_build_args = [clang_path, EMIT_LLVM_FLAG]
    # 1. 添加STM32核心架构参数
    modified_build_args.extend([ARCH_TARGET, STM32_LLVM_ARCH])
    # 2. 添加浮点ABI（针对带FPU的STM32）
    modified_build_args.extend(FLOAT_ABI_FLAGS)
    # 3. 添加STM32编译模式和标准
    modified_build_args.extend(STM32_COMPILE_FLAGS)
    # 4. 添加芯片定义和HAL库宏
    modified_build_args.extend(STM32_DEFINES)
    # 5. 添加调试和优化标志
    modified_build_args.extend(DEBUG_INFO_FLAGS)
    modified_build_args.extend(TARGET_OPTIMIZATION_FLAGS)
    # 6. 添加禁用警告标志
    modified_build_args.extend(DISABLE_WARNINGS)

    # 计算相对目标文件路径，构建位码输出目录（适配STM32构建目录结构）
    rel_obj_file = output_file_path.split(src_build_dir)[-1].lstrip('/\\')  # 兼容Windows路径
    target_out_dir = os.path.join(llvm_bit_code_out, os.path.dirname(rel_obj_file))
    os.makedirs(target_out_dir, exist_ok=True)
    target_bc_file = os.path.join(target_out_dir, f"{os.path.basename(output_file_path)}.bc")

    # 过滤并添加允许的编译参数（适配STM32的GCC参数）
    for curr_op in build_args:
        if _is_allowed_flag(curr_op):
            # 替换ARMCC/GCC的CPU参数为LLVM兼容格式
            if curr_op.startswith('-I'):  # 保留头文件包含路径（STM32 HAL库必备）
                modified_build_args.append(curr_op)
            elif curr_op.startswith('-D') and curr_op not in STM32_DEFINES:  # 保留自定义宏
                modified_build_args.append(curr_op)
            else:
                modified_build_args.append(curr_op)

    # 构建从位码生成目标文件的参数（移除emit-llvm）
    to_obj_from_bc_build_args = modified_build_args.copy()
    to_obj_from_bc_build_args.remove(EMIT_LLVM_FLAG)
    bitcode_to_obj_file_template = to_obj_from_bc_build_args.copy()

    # 构建生成位码的命令
    modified_build_args.extend(["-c", src_file_path, "-o", target_bc_file])
    # 构建直接生成LLVM目标文件的命令（适配STM32目标文件格式）
    to_obj_file_build_args = modified_build_args.copy()
    to_obj_file_build_args.remove(EMIT_LLVM_FLAG)
    to_obj_file_build_args[-1] = f"{target_bc_file[:-3]}.stm32.llvm.obj"  # 明确STM32目标文件后缀
    # 构建从位码生成目标文件的命令
    to_obj_from_bc_build_args.extend(["-c", target_bc_file, "-o", f"{target_bc_file}_stm32_frombc.obj"])

    return (
        work_dir, output_file_path, target_bc_file,
        ' '.join(bitcode_to_obj_file_template),
        ' '.join(modified_build_args),
        ' '.join(to_obj_file_build_args),
        ' '.join(to_obj_from_bc_build_args)
    )


def build_using_clang(
        compile_commands: List[Any],
        original_build_base: str,
        clang_path: str = CLANG_PATH,
        llvm_bc_out: str = "./stm32_llvm_bc_out",
        transformation_so: Optional[str] = None,
        opt_path: Optional[str] = None,
        stm32_arch: str = STM32_LLVM_ARCH,
        stm32_defines: Optional[List[str]] = None
) -> None:
    """
    使用Clang编译STM32代码并生成LLVM位码，可选执行LLVM变换并转换回目标文件
    :param compile_commands: 编译命令列表（包含src_file/output_file/work_dir/curr_args等属性）
    :param original_build_base: 原始构建基础目录
    :param clang_path: Clang二进制路径（建议使用armclang）
    :param llvm_bc_out: LLVM位码输出目录（默认STM32专用目录）
    :param transformation_so: LLVM变换插件(.so)路径
    :param opt_path: LLVM opt工具路径
    :param stm32_arch: STM32架构（覆盖默认值，如armv6-m/armv8-m.main）
    :param stm32_defines: STM32自定义宏定义（覆盖默认值）
    :return: None
    """
    # 全局覆盖STM32架构和宏定义（支持动态传入）
    global STM32_LLVM_ARCH, STM32_DEFINES
    if stm32_arch:
        STM32_LLVM_ARCH = stm32_arch
    if stm32_defines:
        STM32_DEFINES = stm32_defines

    # 创建STM32专用输出目录
    os.makedirs(llvm_bc_out, exist_ok=True)
    output_llvm_sh_file = os.path.join(llvm_bc_out, 'stm32_clang_build.json')
    human_llvm_txt_file = os.path.join(llvm_bc_out, 'stm32_clang_build.txt')

    log_info(f"将STM32编译命令写入JSON文件: {output_llvm_sh_file}")
    log_info(f"将可读格式编译命令写入TXT文件: {human_llvm_txt_file}")

    all_compilation_commands: List[Tuple[str, str]] = []
    target_output_commands: List[Dict[str, str]] = []
    transformation_info: Dict[str, Tuple[str, str]] = {}

    # 处理每个STM32编译命令
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
            log_error(f"处理第{idx}个STM32编译命令失败: {str(e)}，跳过该命令")
            continue

        all_compilation_commands.append((work_dir, target_command_bc_cmd))
        # 构建STM32专用命令字典
        cmd_dict = {
            "stm32_orig_obj_file": orig_output,
            "stm32_to_llvm_bc": target_command_bc_cmd,
            "stm32_to_llvm_obj": target_obj_cmd,
            "stm32_from_llvm_bc_to_obj": target_bc_to_obj_cmd
        }
        target_output_commands.append(cmd_dict)
        transformation_info[orig_output] = (target_bc_file, bitcode_to_obj_file_template)

    # 写入可读格式的TXT文件
    with open(human_llvm_txt_file, 'w', encoding='utf-8') as fp_human_out:
        fp_human_out.write(json.dumps(target_output_commands, indent=4, ensure_ascii=False))

    # 写入JSON文件
    with open(output_llvm_sh_file, 'w', encoding='utf-8') as fp_out:
        json.dump(target_output_commands, fp_out, indent=4, sort_keys=True, ensure_ascii=False)

    # 多进程执行STM32编译命令
    if all_compilation_commands:
        log_info(f"共获取{len(all_compilation_commands)}个STM32编译命令，启动多进程执行")
        with Pool() as p:
            p.map(_run_program, all_compilation_commands)
        log_info("STM32多进程编译命令执行完成")
    else:
        log_info("无STM32编译命令需要执行，跳过多进程步骤")

    # 执行LLVM变换（如果指定了插件和opt路径）
    if transformation_so and opt_path:
        log_info("开始执行STM32 LLVM变换并转换回目标文件")
        for curr_output_obj in transformation_info.keys():
            orig_bc_file, bitcode_to_obj_template = transformation_info[curr_output_obj]
            if not os.path.exists(orig_bc_file):
                log_error(f"STM32位码文件不存在: {orig_bc_file}，跳过变换")
                continue

            # 检查位码文件有效性
            try:
                with open(orig_bc_file, 'rb') as fp:
                    header = fp.read(2)
                    if header != b"BC":
                        log_error(f"STM32位码文件无效: {orig_bc_file}，直接复制原文件")
                        os.system(f"cp {orig_bc_file} {curr_output_obj}")
                        continue

                # 执行STM32专用变换命令
                transformation_bc_file = f"{orig_bc_file}.stm32.transform.bc"
                transformation_command = (
                    f"{opt_path} -load {transformation_so} -logmmio "
                    f"{orig_bc_file} -o {transformation_bc_file}"
                )
                log_info(f"执行STM32变换命令: {transformation_command}")
                os.system(transformation_command)

                # 从变换后的位码生成STM32目标文件
                bc_to_obj_cmd = (
                    f"{bitcode_to_obj_template} -c {transformation_bc_file} "
                    f"-o {curr_output_obj}"
                )
                log_info(f"STM32位码转目标文件: {bc_to_obj_cmd}")
                os.system(bc_to_obj_cmd)
            except Exception as e:
                log_error(f"处理STM32变换文件{orig_bc_file}失败: {str(e)}")
        log_success("STM32 LLVM变换执行完成")
    else:
        log_info("未指定变换插件或opt路径，跳过STM32 LLVM变换步骤")


# 示例调用（STM32专用测试）
if __name__ == "__main__":
    # 模拟STM32编译命令对象
    class MockCompileCommand:
        def __init__(self, curr_args, work_dir, src_file, output_file):
            self.curr_args = curr_args
            self.work_dir = work_dir
            self.src_file = src_file
            self.output_file = output_file

    # 构建STM32模拟编译命令列表（适配F407芯片）
    mock_commands = [
        MockCompileCommand(
            curr_args=[
                "-I./Drivers/STM32F4xx_HAL_Driver/Inc",
                "-I./Core/Inc",
                "-I./Drivers/CMSIS/Device/ST/STM32F4xx/Include",
                "-I./Drivers/CMSIS/Include"
            ],
            work_dir="./STM32F407ZGT6_Project",
            src_file="./Core/Src/main.c",
            output_file="./Build/Objects/main.o"
        )
    ]

    # 调用STM32构建函数
    build_using_clang(
        compile_commands=mock_commands,
        original_build_base="./Build",
        clang_path="clang",  # 实际使用建议替换为armclang路径
        llvm_bc_out="./stm32_llvm_bc_out",
        stm32_arch="armv7e-m",  # STM32F4系列使用armv7e-m
        stm32_defines=[
            '-DSTM32F407xx',
            '-DUSE_HAL_DRIVER',
            '-DHSE_VALUE=8000000'
        ]
        # transformation_so="./stm32_transform.so",  # 实际变换插件
        # opt_path="opt"  # LLVM opt工具路径
    )
