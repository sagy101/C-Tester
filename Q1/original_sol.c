#define _CRT_SECURE_NO_WARNINGS

#include <stdio.h>

int main() {
	int num = 0, i;
	scanf("%d", &num);
	if (num == 0){ ///if num is zero we end
		printf("%d has no Divisors!\n" , num);
	}
	else{
		printf("Divisors of %d are: ",num);
		for (i=1;i<=num;i++) {
			if (num%i == 0) { ///if % is 0 so the number is divisor
				printf("%d ",i);
			}
		}
		printf("\n");
	}
	return 0;
}