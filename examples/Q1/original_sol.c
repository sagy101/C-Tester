#include <stdio.h>

int main(void) {
    int value;
    if (scanf("%d", &value) != 1) {
        return 1;
    }

    printf("%d\n", value * 2);
    return 0;
}
