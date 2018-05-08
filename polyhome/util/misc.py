import random
import hashlib


#大金空调室内机状态寄存器地址正向映射表
sDaiKinInnerStateMap = {}
#大金空调室内机状态寄存器地址逆向映射表
sDaiKinInnerStateMapReverse = {}
#大金空调室内机控制寄存器地址正向映射表
sDaiKinInnerControlMap = {}
#大金空调室内机控制寄存器地址逆向映射表
sDaiKinInnerControlMapReverse = {}

for i in range(1, 6):
    for j in range(16):
        lis = []
        lis.append(str(i))
        lis.append('-')
        lis.append(str(j))
        #初始化室内机状态寄存器地址映射表
        sDaiKinInnerStateMap[''.join(lis)] = 32001 + ((i - 1) * 96) + (j * 6)
        sDaiKinInnerStateMapReverse[32001 + ((i - 1) * 96) + (j * 6)] = ''.join(lis)
        #初始化室内机控制寄存器地址映射表
        sDaiKinInnerControlMap[''.join(lis)] = 42001 + ((i - 1) * 48) + (j * 3)
        sDaiKinInnerControlMapReverse[42001 + ((i - 1) * 48) + (j * 3)] = ''.join(lis)

"""n int random"""
def randomnint(n):
    if n <= 0:
        return None
    lis = []
    for i in range(n):
        lis.append(str(random.randint(0, 9)))
    return ''.join(lis)

"""md5"""
def md5str(s):
    return hashlib.md5(s.encode(encoding='UTF-8')).hexdigest().lower()

"""startAddrSwitch"""
def startaddrswitch(startaddr):
    hexintstr = hex(startaddr).replace('0x', '')
    while len(hexintstr) < 4:
        hexintstr = '0'+hexintstr
    print('hexintstr == '+hexintstr)
    hig8 = hexintstr[0:2]
    low8 = hexintstr[2:]
    return [int(hig8, 16), int(low8, 16)]

"""int to bin 16 str reverse"""
def inttobin16str_reverse(incount):
    strbin = bin(incount).replace('0b', '')
    while len(strbin) < 16:
        strbin = '0'+strbin
    return strbin[::-1]

"""int to bin 16 str no reverse"""
def inttobin16str_noreverse(incount):
    strbin = bin(incount).replace('0b', '')
    while len(strbin) < 16:
        strbin = '0'+strbin
    return strbin



