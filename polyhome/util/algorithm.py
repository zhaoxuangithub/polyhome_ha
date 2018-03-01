def xorcrc_str(data): 
    result = int(data[0], 16)
    for index in range(0, len(data) - 2):
        result ^= int(data[index + 1], 16)
    return result

def xorcrc_hex(data): 
    result = int(data[0])
    for index in range(0, len(data) - 2):
        result ^= int(data[index + 1])
    return result

def calculateCRC(data_array):
    datalist = data_array
    index = 0
    try:
        for index, item in enumerate(datalist):
            datalist[index] = item
        temp = calculateonebyte(datalist.pop(0), 0xFFFF)
        for data in datalist:
            temp = calculateonebyte(data, temp)
        return temp
    except ValueError as err:
        pass

def calculateonebyte(databyte, tempcrc): 
    if not 0x00 <= databyte <= 0xFF:
        raise Exception((u'data：0x{0:<02X} is not [0x00-0xFF]'.format(databyte)).encode('utf-8'))

    low_byte = (databyte ^ tempcrc) & 0x00FF
    result_crc = (tempcrc & 0xFF00) | low_byte

    for index in range(8):
        if result_crc & 0x0001 == 1:
            result_crc >>= 1
            result_crc ^= 0xA001
        else:
            result_crc >>= 1

    return result_crc

def crc_1byte(data):
    crc_1byte = 0
    for i in range(0, 8):
        if ((crc_1byte^data)&0x01):
            crc_1byte ^= 0x18
            crc_1byte >>= 1
            crc_1byte |= 0x80
        else:
            crc_1byte >>= 1
    return crc_1byte

def crc8(data):
    ret = 0
    for byte in data:
        ret = (crc_1byte(ret^byte))
    return ret

def sumup(data):
    ret = 0
    for byte in data:
        ret += byte
    return ret