Punto 4 Esclaco: #include <msp430.h>

volatile unsigned int recibidos = 0;
volatile unsigned char terminar = 0;
volatile char ultimo_dato;
void config_timer(void);

int main(void) {
    WDTCTL = WDTPW | WDTHOLD;

    UCSCTL3 |= SELREF__REFOCLK;
    UCSCTL4 |= SELA__REFOCLK;

    P3SEL |= BIT3 | BIT4;
    UCA0CTL1 |= UCSWRST;
    UCA0CTL1 |= UCSSEL__SMCLK;
    UCA0BR0 = 104;
    UCA0BR1 = 0;
    UCA0MCTL = UCBRS_1;
    UCA0CTL1 &= ~UCSWRST;
    UCA0IE |= UCRXIE;

    P1DIR |= BIT0;
    P1OUT &= ~BIT0;

    config_timer();
    __enable_interrupt();

    while(1) {
        if(terminar == 1) {
            P1OUT |= BIT0;
            __delay_cycles(800000);
            P1OUT &= ~BIT0;

            recibidos = 0;
            terminar = 0;
            TA0R = 0;
        }
        __bis_SR_register(LPM0_bits + GIE);
    }
}

void config_timer(void) {
    TA0CTL = TASSEL__ACLK + MC__UP + TACLR;
    TA0CCR0 = 120000;
    TA0CCTL0 = CCIE;
}

#pragma vector=USCI_A0_VECTOR
__interrupt void USCI_A0_ISR(void) {
    switch(__even_in_range(UCA0IV, 4)) {
        case 2:
            if(UCA0STAT & UCOE) {
                terminar = 1;
            } else {
                ultimo_dato = UCA0RXBUF;
                recibidos++;
                TA0R = 0;

                if(ultimo_dato == 'S') {
                    terminar = 1;
                }
                else if(recibidos >= 20) {
                    terminar = 1;
                }
            }
            __bic_SR_register_on_exit(LPM0_bits);
            break;
    }
}

#pragma vector=TIMER0_A0_VECTOR
__interrupt void Timer_A_ISR(void) {
    terminar = 1;
    __bic_SR_register_on_exit(LPM0_bits);
}
