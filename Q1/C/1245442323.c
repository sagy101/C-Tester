#define _CRT_SECURE_NO_WARNINGS

#include <stdio.h>

int main()
{
	int n;
	printf("Input: n = ");
	scanf("%d", &n);
	printf("Output: ");
	if(n < 0) {
	    printf("%d ", 1);
	    return 0;
	}
	for (int i = 1; i <= n; i++) {
        if (n % i == 0) {
            printf("%d ", i);
        }
    }
	return 0;
}