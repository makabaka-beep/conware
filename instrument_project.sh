#!/usr/bin/env bash

# ========== 1. 日志函数定义（统一输出格式） ==========
log_info() {
    echo -e "[*]  $1"
}

log_error() {
    echo -e "[!]  $1"
}

log_success() {
    echo -e "[+]  $1"
}

# ========== 2. 参数校验（适配 STM32 工程路径） ==========
if [ "$#" -ne 1 ]; then
    echo "Usage: $0 <path to STM32F408 project>"
    echo "Example: $0 /home/makabaka/conware/firmware/stm32f408_project"
    exit 1
fi

# ========== 3. 路径定义（替换 Arduino 为 STM32F408） ==========
# 脚本绝对路径
SCRIPT=$(readlink -f "$0")
SCRIPTPATH=$(dirname "$SCRIPT")
# STM32 工程根路径（用户传入的参数）
STM32_PROJ_PATH=$(realpath "$1")
# STM32 工程名称
STM32_PROJ_NAME=$(basename "$STM32_PROJ_PATH")
# STM32 核心源码文件（可根据工程调整，如 main.c）
STM32_MAIN_FILE="$STM32_PROJ_PATH/src/main.c"
# 插桩后编译产物输出路径
BUILD_PATH="$STM32_PROJ_PATH/build_instrumented"
# 临时编译目录
tmpbuild="/tmp/conware_stm32_build"

# ========== 4. LLVM 插件路径（关键修复：匹配实际生成路径） ==========
LLVM_TRANSFORMATION_LIB="$SCRIPTPATH/llvm_build_infra/llvm_transformation_passes/build/MMIOLogger/libMMIOLogger.so"
# LLVM opt 工具路径（适配本地 LLVM 7.0.1）
LLVM_OPT_PATH="$SCRIPTPATH/runtime/llvm-7.0.1.obj/bin/opt"

# ========== 5. 前置校验（确保 STM32 工程有效） ==========
# 检查核心源码文件是否存在
if [ ! -f "$STM32_MAIN_FILE" ]; then
    log_error "STM32 main file $STM32_MAIN_FILE does not exist!"
    exit 1
fi

# 检查 LLVM 插件是否存在（友好提示，而非直接退出）
if [ ! -f "$LLVM_TRANSFORMATION_LIB" ]; then
    log_error "LLVM Transformation so file doesn't exist: $LLVM_TRANSFORMATION_LIB"
    log_info "Will continue build without LLVM instrumentation..."
fi

# 检查 LLVM opt 工具是否存在
if [ ! -f "$LLVM_OPT_PATH" ]; then
    log_warning "LLVM opt tool not found at $LLVM_OPT_PATH, use system opt instead"
    LLVM_OPT_PATH="opt"
fi

# ========== 6. 插桩编译（适配 STM32 工程的插桩脚本） ==========
log_info "Temporary build dir: $tmpbuild, Output dir: $BUILD_PATH"
log_info "Instrumenting STM32F408 project: $STM32_PROJ_NAME ..."

# 执行 LLVM 插桩脚本（替换 Arduino 插桩参数为 STM32 参数）
# -i: STM32 核心源码文件  -b: 临时编译目录  -r: 脚本根路径  -o: 最终构建目录
# 新增插件路径参数：-s LLVM_TRANSFORMATION_LIB -t LLVM_OPT_PATH
python3 "$SCRIPTPATH/llvm_build_infra/instrument_stm32_project.py" \
    -i "$STM32_MAIN_FILE" \
    -b "$tmpbuild" \
    -r "$SCRIPTPATH" \
    -o "$BUILD_PATH" \
    -s "$LLVM_TRANSFORMATION_LIB" \
    -t "$LLVM_OPT_PATH"

# 检查插桩脚本执行结果
if [ $? -ne 0 ]; then
    log_error "STM32 instrumentation script failed!"
    exit 1
fi

# ========== 7. 产物复制与清理 ==========
# 创建输出目录（确保存在）
mkdir -p "$BUILD_PATH"
# 复制插桩后的编译产物（适配STM32产物类型：elf/hex/bin/o）
cp -a "$tmpbuild"/*.elf "$tmpbuild"/*.hex "$tmpbuild"/*.bin "$tmpbuild"/*.o "$BUILD_PATH/" 2>/dev/null
# 清理临时目录
rm -rf "$tmpbuild"

log_success "Success! Instrumented STM32F408 project output to: $BUILD_PATH"
exit 0

