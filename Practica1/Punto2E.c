Punto 2 Esclavo:
#include <msp430.h>

void main(void) {
    WDTCTL = WDTPW | WDTHOLD;
    P1DIR |= BIT0;
    P1OUT &= ~BIT0;
    P3SEL |= BIT3 | BIT4;
    UCA0CTL1 |= UCSWRST;
    UCA0CTL1 |= UCSSEL_2;
    UCA0BR0 = 104;              // Cambio a 9600 baudios
    UCA0BR1 = 0;
    UCA0MCTL |= UCBRS_1 + UCBRF_0;
    UCA0CTL0 = UCSPB;
    UCA0CTL1 &= ~UCSWRST;
    UCA0IE |= UCRXIE;

    __bis_SR_register(LPM0_bits + GIE);
}

#pragma vector=USCI_A0_VECTOR
__interrupt void USCI_A0_ISR(void) {
    switch(__even_in_range(UCA0IV, 4)) {
        case 2:
            if(UCA0RXBUF == 'A') P1OUT ^= BIT0;
            break;
    }
}
