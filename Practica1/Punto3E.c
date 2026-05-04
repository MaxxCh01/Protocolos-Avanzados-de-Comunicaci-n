Punto 3 Esclavo: #include <msp430.h>

void main(void) {
    WDTCTL = WDTPW | WDTHOLD;
    P1DIR |= BIT0;
    P1OUT &= ~BIT0;
    P3SEL |= BIT3 | BIT4;
    UCA0CTL1 |= UCSWRST;
    UCA0CTL1 |= UCSSEL_2;
    UCA0BR0 = 104;
    UCA0BR1 = 0;
    UCA0MCTL |= UCBRS_1 + UCBRF_0;

    // Paridad Par, 1 bit de parada
    UCA0CTL0 = UCPEN | UCPAR;

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
