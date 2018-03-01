"""
{:mobile => 18030405923}

# 转json
json_str = {:mobile => 18030405923}.to_json
=> "{\"mobile\":18030405923}"

# 加密串(32位)
private_key = "GjcfbhCIJ2owQP1Kxn64DqSk5X4YRZ7u"

# 加密过程
# 第一步:将参数json字符串和加密串拼接在一起组成新的字符串(for_sign_str)
for_sign_str = json_str + private_key
# 第二步:将拼接后的字符串 MD5加密之后得到最后的签名字符串（sign_str）
sign_str = Digest::MD5.hexdigest(for_sign_str).downcase
=> "a44a9529a532bfd612b42e38be1410f9"

# 最终提交参数：
{
  sign: sign_str,
  data: json_str
}
"""
def http_api_sign(data):
    print('sign')