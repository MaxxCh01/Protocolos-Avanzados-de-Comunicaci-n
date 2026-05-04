//Maestro punto 1: #include <msp430.h>
void main(void) {

    WDTCTL = WDTPW | WDTHOLD;
    P3SEL |= BIT3 | BIT4;
    UCA0CTL1 |= UCSWRST;
    UCA0CTL1 |= UCSSEL_2;
    UCA0BR0 = 8;
    UCA0BR1 = 0;
    UCA0MCTL |= UCBRS_6 + UCBRF_0;
    UCA0CTL0 = UCSPB;
    UCA0CTL1 &= ~UCSWRST;
    while(1) {
        while (!(UCA0IFG & UCTXIFG));
        UCA0TXBUF = 'A';
        __delay_cycles(100000);
    }
}
