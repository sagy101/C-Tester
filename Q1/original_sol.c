#define _CRT_SECURE_NO_WARNINGS


#include <stdio.h>
#include <math.h>

// NOTE: Since <math.h> is included, you can use sqrt() to calculate the square-root of a number.

int q_1(int num);

int q_2(int num);

int q_3(int num);

int main()
{
    int q_num = 0, n = 0, res = 0;

    printf("Which question would you like to check?: \n");
    scanf("%d", &q_num);
    printf("Please enter a number: \n");
    scanf("%d", &n);
    switch (q_num)
    {
    case 1:
        res = q_1(n);
        printf("Result = %d \n", res);
        break;
    case 2:
        res = q_2(n);
        printf("Result = %d \n", res);
        break;
    case 3:
        res = q_3(n);
        printf("Result = %d \n", res);
        break;
    default:
        printf("%d is an invalid input \n", q_num);
    }
    return 0;
}

int q_1(int num)
{
    if (num == 0) {
        return 0;
    }
    // Recursive step: Get the binary representation of n / 2
    int result = q_1(num / 2);

    // Append the current bit (n % 2) to the result
    // Shift result left by 1 and add the current bit (n % 2)
    return result * 10 + (num % 2);

}

int q_2(int num)
{
    // Handle negative inputs (optional)
    if (num < 0) num = -num;

    // Base case: already a single digit
    if (num < 10) {
        return num;
    }

    // Sum this level’s digits
    int sum = (num % 10) + q_2(num / 10);

    // If that sum is still more than one digit, recurse again
    return q_2(sum);
}

int q_3_helper(int num, int sign) {
    // Base case: If num is 0, return 0
    if (num == 0) {
        return 0;
    }

    // Recursive case: calculate the sum for n-1 and alternate the sign
    int currentTerm = sign * (num * num);
    // Recursive call, passing the opposite sign (-sign) to alternate the sign
    return currentTerm + q_3_helper(num - 1, -1 * sign);
}

int q_3(int num)
{
    return q_3_helper(num, 1);
}


