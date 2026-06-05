def add(a: float, b: float) -> float:
    """
    Adds two numbers and returns their sum.

    Use this operation when combining quantities, totaling prices,
    aggregating counts, or any scenario requiring summation.

    Args:
        a (float): The first operand (augend).
        b (float): The second operand (addend).

    Returns:
        float: The sum of a and b (a + b).

    Example:
        >>> add(349, 829)
        1178.0
    """
    return float(a) + float(b)


def subtract(a: float, b: float) -> float:
    """
    Subtracts b from a and returns the difference.

    Use this operation when finding the remainder after removal,
    applying discounts, computing differences, or net values.

    Args:
        a (float): The minuend (value to subtract from).
        b (float): The subtrahend (value to subtract).

    Returns:
        float: The difference a - b.

    Example:
        >>> subtract(1178.0, 82.46)
        1095.54
    """
    return float(a) - float(b)


def multiply(a: float, b: float) -> float:
    """
    Multiplies two numbers and returns their product.

    Use this operation for scaling values, computing percentages
    (before dividing), finding areas, or repeated addition.

    Args:
        a (float): The first factor (multiplicand).
        b (float): The second factor (multiplier).

    Returns:
        float: The product of a and b (a * b).

    Example:
        >>> multiply(1178.0, 7)
        8246.0
    """
    return float(a) * float(b)


def divide(a: float, b: float) -> float:
    """
    Divides a by b and returns the quotient.

    Use this operation for computing averages, converting percentages
    (divide by 100), splitting values, or finding ratios.

    Args:
        a (float): The dividend (value to divide).
        b (float): The divisor (value to divide by). Must not be zero.

    Returns:
        float: The quotient a / b.

    Raises:
        ValueError: If b is zero, as division by zero is undefined.

    Example:
        >>> divide(8246.0, 100)
        82.46
    """
    if float(b) == 0:
        raise ValueError("Division by zero is undefined.")
    return float(a) / float(b)
