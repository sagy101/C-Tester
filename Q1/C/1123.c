#define _CRT_SECURE_NO_WARNINGS

#include <stdio.h>

int main()
{
	int n, i;
	printf("Input: n = ");
	scanf("%d", &n);
	printf("Output: ");
	for (i = 1; i <= n; i++) {
        if (n % i == 0) {
            printf("%d ", i);
        }
    }
	return 0;
}