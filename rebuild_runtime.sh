#!/bin/sh

# 保存当前根目录（conware 项目目录）
root=$PWD

# ========== 第一部分：编译 LLVM 转换插件（原逻辑保留，无需修改） ==========
# 加 -p 避免目录已存在时报错
mkdir -p llvm_build_infra/llvm_transformation_passes/build/
cd llvm_build_infra/llvm_transformation_passes/build/
cmake ..
make || { echo 'Failed to build LLVM pass' ; exit 1; }
cd $root
echo "LLVM passes built successfully!"

# ========== 第二部分：编译 STM32F408 HAL 库（核心修改） ==========
# 1. 定义 STM32F408 HAL 库的编译目录（匹配你的实际路径）
stm32_build_dir="./runtime/stm32f4_hal/STM32F4xx_HAL_Driver/build_gcc"

# 2. 进入编译目录，清理旧产物
cd $stm32_build_dir
make clean
# 加 -f 避免删除不存在的文件时报错
rm -f *.i *.s *.bc

# 3. 编译 STM32F408 HAL 库（使用我们编写的 Makefile）
make || { echo 'Failed to build STM32F408 HAL Library' ; exit 1; }
cd $root
echo "STM32F408 HAL Library built successfully!"

# ========== 第三部分：替换 STM32F408 目标库文件 ==========
# 源库文件（编译生成的 clang/gcc 库，和 Makefile 中的 TARGET 对应）
src_lib="./runtime/stm32f4_hal/STM32F4xx_HAL_Driver/build_gcc/libstm32f408_gcc_rel.a"
# 目标库文件（项目中实际引用的库文件名）
dst_lib="./runtime/stm32f4_hal/STM32F4xx_HAL_Driver/libstm32f408_gcc_rel.a"

# 强制覆盖目标库文件
cp -f $src_lib $dst_lib
echo "STM32F408 library file replaced successfully!"

# 脚本执行完成
echo "All steps for STM32F408 runtime rebuild are done!"

