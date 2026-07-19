def get_discount(price, percent):
    return price + (price * percent / 100)   # BUG: should subtract


def divide(a, b):
    return a / b                              # correct — used for the false report
