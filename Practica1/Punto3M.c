Punto 3 Maestro:
#include <msp430.h>

void main(void) {
    WDTCTL = WDTPW | WDTHOLD;
    P3SEL |= BIT3 | BIT4;
    UCA0CTL1 |= UCSWRST;
    UCA0CTL1 |= UCSSEL_2;
    UCA0BR0 = 104;
    UCA0BR1 = 0;
    UCA0MCTL |= UCBRS_1 + UCBRF_0;

    //Paridad Par habilitada, 8 bits, 1 bit de parada
    UCA0CTL0 = UCPEN | UCPAR;

    UCA0CTL1 &= ~UCSWRST;

    while(1) {
        while (!(UCA0IFG & UCTXIFG));
        UCA0TXBUF = 'A';
        __delay_cycles(100000);
    }
}
