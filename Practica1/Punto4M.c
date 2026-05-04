Punto 4 Maestro (3 condiciones):
#include <msp430.h>

void config_uart_tx(void);
void enviar_char(char c);

int main(void)
{
    WDTCTL = WDTPW | WDTHOLD;
    config_uart_tx();

    char mensaje[] = {'5','2','1','1','2','S'};
    int i;

    while(1)
    {
        for(i = 0; i < sizeof(mensaje); i++)
        {
            enviar_char(mensaje[i]);
            __delay_cycles(1000000);
        }
    }
}

void config_uart_tx(void)
{
    P3SEL |= BIT3 | BIT4;
    UCA0CTL1 |= UCSWRST;
    UCA0CTL1 |= UCSSEL__SMCLK;
    UCA0BR0 = 104;
    UCA0BR1 = 0;
    UCA0MCTL = UCBRS_1;
    UCA0CTL1 &= ~UCSWRST;
}

void enviar_char(char c)
{
    while(!(UCA0IFG & UCTXIFG));
    UCA0TXBUF = c;
}
