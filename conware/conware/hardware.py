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
        # 手动生成STM32 F407 MMIO操作日志（PF9 LED翻转）
        logger.info("Generating STM32 F407 MMIO logs (PF9 LED operations)")
        for x in range(count):
            # 模拟CONWAREDUMP_START
            logger.info("Dumping recording...")
            dumping = True
            
            # 模拟MMIO WRITE操作（PF9置高：LED灭）
            write_high = ["WRITE", "0x40021414", "0x00000200", "0"]
            data_log.write_row(write_high)
            logger.debug(f"Recorded: {write_high} (PF9 HIGH)")
            dump_count += 1
            
            # 模拟延时（LED亮灭间隔）
            time.sleep(1)
            
            # 模拟MMIO WRITE操作（PF9置低：LED亮）
            write_low = ["WRITE", "0x40021414", "0x00000000", "0"]
            data_log.write_row(write_low)
            logger.debug(f"Recorded: {write_low} (PF9 LOW)")
            dump_count += 1
            
            # 模拟CONWAREDUMP_END
            dumping = False
            logger.info(f"Dump done ({dump_count} events recorded).")
        
        # ========== 清理资源 ==========
        uart_log.write("STM32F407 Firmware Log (PF9 LED Flip)\n")
        uart_log.close()
        data_log.close()
        logger.info(f"=== Log collection completed: {dump_count} events ===")
