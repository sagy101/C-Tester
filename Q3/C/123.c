#define _CRT_SECURE_NO_WARNINGS

#include <stdio.h>

int main()
{
	int n, t;
    printf("Enter a number1: ");
    scanf("%d", &n);
    printf("Enter a number2: ");
    scanf("%d", &t);
    if(n>50) n += 10;
    printf("Sum: %d", n+t);
	return 0;
}