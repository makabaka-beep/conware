// 极简STM32F408裸机代码（完整版本，必包含以下内容）
#define PERIPH_BASE        0x40000000UL
#define AHB1PERIPH_BASE    (PERIPH_BASE + 0x00020000UL)
#define GPIOA_BASE         (AHB1PERIPH_BASE + 0x0000UL)
#define RCC_BASE           (AHB1PERIPH_BASE + 0x3800UL)

// 寄存器定义
#define RCC_AHB1ENR        (*((volatile unsigned int *)(RCC_BASE + 0x30)))
#define GPIOA_MODER        (*((volatile unsigned int *)(GPIOA_BASE + 0x00)))
#define GPIOA_ODR          (*((volatile unsigned int *)(GPIOA_BASE + 0x14)))

// 延时函数
void delay(void) {
    volatile unsigned int i;
    for(i=0; i<500000; i++);
}

int main(void) {
    // 使能GPIOA时钟
    RCC_AHB1ENR |= (1 << 0);
    // 设置PA5为输出模式（通用推挽）
    GPIOA_MODER &= ~(3 << 10);  // 清除原有配置
    GPIOA_MODER |= (1 << 10);   // 设置为输出模式
    
    while(1) {
        // 翻转PA5电平（LED闪烁）
        GPIOA_ODR ^= (1 << 5);
        delay();
    }
}

// 复位处理函数（程序入口，必须命名为Reset_Handler）
void Reset_Handler(void) {
    main();
    while(1);
}

// 中断向量表（必须放在.isr_vector段，指定栈顶地址）
__attribute__((section(".isr_vector"), used))
void (* const g_pfnVectors[])(void) = {
    (void (*)(void))0x20020000,  // STM32F408栈顶地址（RAM末尾）
    Reset_Handler               // 复位中断（第一个中断）
};

