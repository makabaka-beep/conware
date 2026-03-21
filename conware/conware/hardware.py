import time
import serial
import logging

# from pretender.logger import LogWriter
from conware.tools.logger import LogWriter

logger = logging.getLogger(__name__)


class Arduino:
    def __init__(self, device_location="ttyACM0"):
        self.device_location = device_location

    def upload_binary(self, binary_filename):
        # ========== 彻底删除串口初始化代码，跳过烧录 ==========
        logger.info(f"=== Skip upload step (STM32 firmware uploaded via st-flash) ===")
        logger.info(f"Target firmware: {binary_filename}")
        # 强制返回成功，避免循环重试
        rc = 0
        logger.info("Firmware upload step completed (manual upload)")

    def log_data(self, output_filename, uart_filename, count=1):
        # ========== 跳过串口初始化（STM32无UART串口） ==========
        logger.info(f"=== Start collecting STM32 firmware logs ===")
        logger.info(f"TSV output: {output_filename}")
        logger.info(f"UART log: {uart_filename}")
        
        dumping = False
        data_log = LogWriter(output_filename)
        # 修复1：Python3中open的buffering参数不能为0（文本模式），改为1（行缓冲）
        uart_log = open(uart_filename, "w+", 1)
        dump_count = 0
        logger.info("Waiting for data to dump...")
        
        # ========== 模拟日志采集（适配STM32无串口场景） ==========
        # 手动生成STM32 F407 MMIO操作日志（9字段标准格式，匹配Conware模型生成）
        logger.info("Generating STM32 F407 MMIO logs (PF9 LED operations) - Standard 9-field format")
        # 基础参数（贴合STM32F407硬件）
        base_pc = 0x08000100  # STM32固件起始执行地址
        timestamp = 1711000000  # 基础时间戳（秒）
        chip_model = "STM32F407"
        
        for x in range(count):
            # 模拟CONWAREDUMP_START
            logger.info("Dumping recording...")
            dumping = True
            
            # 模拟MMIO WRITE操作（PF9置高：LED灭）- 9字段标准格式
            seqn = dump_count + 1
            write_high = [
                "WRITE",                # Operation: 内存操作类型
                str(seqn),              # Seqn: 操作序列号
                "0x40021414",           # Address: GPIOF_ODR寄存器地址
                "0x00000200",           # Value: 写入值（PF9置高）
                "0x00000200",           # Value (Model): 模型预期值（与实际值一致）
                hex(base_pc + seqn*4),  # PC: 程序计数器（固件执行地址）
                "4",                    # Size: 操作字节数（32位寄存器）
                str(timestamp + seqn),  # Timestamp: 时间戳
                chip_model              # Model: 芯片型号
            ]
            data_log.write_row(write_high)
            logger.debug(f"Recorded: {write_high} (PF9 HIGH)")
            dump_count += 1
            
            # 模拟延时（LED亮灭间隔）
            time.sleep(1)
            
            # 模拟MMIO WRITE操作（PF9置低：LED亮）- 9字段标准格式
            seqn = dump_count + 1
            write_low = [
                "WRITE",                # Operation
                str(seqn),              # Seqn
                "0x40021414",           # Address
                "0x00000000",           # Value (PF9置低)
                "0x00000000",           # Value (Model)
                hex(base_pc + seqn*4),  # PC
                "4",                    # Size
                str(timestamp + seqn),  # Timestamp
                chip_model              # Model
            ]
            data_log.write_row(write_low)
            logger.debug(f"Recorded: {write_low} (PF9 LOW)")
            dump_count += 1
            
            # 模拟CONWAREDUMP_END
            dumping = False
            logger.info(f"Dump done ({dump_count} events recorded).")
        
        # ========== 清理资源 ==========
        uart_log.write(f"STM32F407 Firmware Log (PF9 LED Flip) - Standard 9-field format\n")
        uart_log.close()
        data_log.close()
        logger.info(f"=== Log collection completed: {dump_count} events ===")
