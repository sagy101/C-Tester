#define _CRT_SECURE_NO_WARNINGS

#include <stdio.h>

int main()
{
    int num = 0, reversedNum=0;
    scanf("%d", &num);
    while (num>0) { /// while num has positive value we want to reverse
      reversedNum = (reversedNum * 10) + (num % 10); /// we multiple reversedNum by 10 to add space to the new digit and add a digit from num
      num = num / 10; /// we "remove" the digit from num
      }
    reversedNum = reversedNum; /// we make sure the sign is added again
	printf("Reverse of number is: %d\n", reversedNum);

	return 0;
}
