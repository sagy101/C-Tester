#define _CRT_SECURE_NO_WARNINGS

#include <stdio.h>

int main(
{
	int n, reverse = 0;
    printf("Enter a number to reverse: ");
    scanf("%d", &n);

    while (n != 0) {
        reverse = reverse * 10 + n % 10;
        n /= 10;
    }
    printf("Reverse of number is: %d", reverse);
	return 0;
}