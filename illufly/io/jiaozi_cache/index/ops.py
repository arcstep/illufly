
# 单值比较操作符
COMPARE_OPS = {
    "==": lambda x, y: x == y,
    "!=": lambda x, y: x != y,
    ">=": lambda x, y: x >= y,
    "<=": lambda x, y: x <= y,
    ">": lambda x, y: x > y,
    "<": lambda x, y: x < y
}

# 区间比较操作符
RANGE_OPS = {
    "[]": lambda x, start, end: start <= x <= end,  # 闭区间
    "()": lambda x, start, end: start < x < end,    # 开区间
    "[)": lambda x, start, end: start <= x < end,   # 左闭右开
    "(]": lambda x, start, end: start < x <= end    # 左开右闭
}
