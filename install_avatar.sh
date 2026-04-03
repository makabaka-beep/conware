#!/bin/sh

# 设置错误时退出（可选）
set -e

# 获取Python 3的site-packages路径
get_python3_site_packages() {
    if [ -n "$VIRTUAL_ENV" ]; then
        # 在虚拟环境中，自动检测Python版本
        PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
        echo "$VIRTUAL_ENV/lib/python$PYTHON_VERSION/site-packages"
    else
        # 系统Python 3
        python3 -c "import site; print(site.getsitepackages()[0])"
    fi
}

# 检查是否在虚拟环境中
if [ -z "$VIRTUAL_ENV" ]; then
    echo "警告: 未检测到虚拟环境，建议先激活虚拟环境"
    echo "运行: source conware-venv/bin/activate"
fi

# init sub modules
echo "初始化Git子模块..."
git submodule init
git submodule update --init --recursive
cd avatar2-pretender
git checkout master
git pull
cd ..

# Install dependencies
echo "安装avatar2-pretender依赖..."
pip3 install -e .

# Fix keystone - 使用动态获取的路径
echo "修复keystone..."
SITE_PACKAGES=$(get_python3_site_packages)
if [ -d "$SITE_PACKAGES/keystone" ]; then
    cp "$SITE_PACKAGES/keystone/"* "$SITE_PACKAGES/keystone/" 2>/dev/null || echo "Keystone复制完成（可能文件已存在）"
    echo "Keystone修复完成"
else
    echo "警告: keystone目录不存在，跳过修复"
fi

# Build qemu
echo "编译QEMU..."
pwd
cd ./targets/src/avatar-qemu/
git submodule update --init dtc
cd ../../
mkdir -p build
mkdir -p build/qemu
cd build/qemu
../../src/avatar-qemu/configure --disable-sdl --target-list=arm-softmmu
make -j
cd ../../..

# Install gdb
echo "安装gdb-multiarch..."
sudo apt-get update
sudo apt-get install -y gdb-multiarch

# Install openocd
echo "安装OpenOCD..."
cd openocd
sudo apt-get install -y python3-hidapi
git checkout edb6796
./bootstrap
./configure --enable-cmsis-dap --enable-jaylink
make -j
sudo make install
cd ..

# Install pretender dependencies
echo "安装Pretender依赖..."
cd pretender
git checkout graphFork
pip3 install -r requirements.txt
pip3 install -e .
cd ..

# Install main project dependencies
echo "安装主项目依赖..."
pip3 install -r requirements.txt

echo "========================================="
echo "安装完成！"
echo "当前虚拟环境: $VIRTUAL_ENV"
echo "Python路径: $(which python3)"
echo "site-packages路径: $(get_python3_site_packages)"
echo "========================================="
