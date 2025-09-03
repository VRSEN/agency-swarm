def sum_of_squares(n):
    return sum(i * i for i in range(1, n + 1))


result = sum_of_squares(35)
print(result)
