import random
import hashlib

"""n int random"""
def randomnint(n):
    if n <= 0:
        return None
    lis = []
    for i in range(n):
        lis.append(str(random.randint(0,9)))
    return ''.join(lis)

"""md5"""
def md5str(s):
    return hashlib.md5(s.encode(encoding='UTF-8')).hexdigest().lower()
