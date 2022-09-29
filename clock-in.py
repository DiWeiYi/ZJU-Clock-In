# -*- coding: utf-8 -*-

# 打卡脚修改自ZJU-nCov-Hitcarder的开源代码，感谢这位同学开源的代码
import urllib
import urllib.request
import hashlib
import requests
import json
import re
import datetime
import time
import sys
import smtplib
from email.mime.text import MIMEText
from email.header import Header
import argparse
# import ddddocr

statusStr = {
    '0': '短信发送成功',
    '-1': '参数不全',
    '-2': '服务器空间不支持,请确认支持curl或者fsocket,联系您的空间商解决或者更换空间',
    '30': '密码错误',
    '40': '账号不存在',
    '41': '余额不足',
    '42': '账户已过期',
    '43': 'IP地址限制',
    '50': '内容含有敏感词'
    }

class ClockIn(object):
    """Hit card class
    Attributes:
        username: (str) 浙大统一认证平台用户名（一般为学号）
        password: (str) 浙大统一认证平台密码
        LOGIN_URL: (str) 登录url
        BASE_URL: (str) 打卡首页url
        SAVE_URL: (str) 提交打卡url
        HEADERS: (dir) 请求头
        sess: (requests.Session) 统一的session
    """
    LOGIN_URL = "https://zjuam.zju.edu.cn/cas/login?service=https%3A%2F%2Fhealthreport.zju.edu.cn%2Fa_zju%2Fapi%2Fsso%2Findex%3Fredirect%3Dhttps%253A%252F%252Fhealthreport.zju.edu.cn%252Fncov%252Fwap%252Fdefault%252Findex"
    BASE_URL = "https://healthreport.zju.edu.cn/ncov/wap/default/index"
    SAVE_URL = "https://healthreport.zju.edu.cn/ncov/wap/default/save"
    CAPTCHA_URL = 'https://healthreport.zju.edu.cn/ncov/wap/default/code'
    HEADERS = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/75.0.3770.100 Safari/537.36"
    }
    
    def __init__(self, username, password):
        self.username = username
        self.password = password
        self.content_ok = "【ZJU自动打卡通知】今日已为您自动打卡"
        self.content_fail = "【ZJU自动打卡通知】自动打卡失败，请在github上检查原因"
        self.sess = requests.Session()
#         self.ocr = ddddocr.DdddOcr()

    def login(self):
        """Login to ZJU platform"""
        res = self.sess.get(self.LOGIN_URL, headers=self.HEADERS)
        execution = re.search(
            'name="execution" value="(.*?)"', res.text).group(1)
        res = self.sess.get(
            url='https://zjuam.zju.edu.cn/cas/v2/getPubKey', headers=self.HEADERS).json()
        n, e = res['modulus'], res['exponent']
        encrypt_password = self._rsa_encrypt(self.password, e, n)

        data = {
            'username': self.username,
            'password': encrypt_password,
            'execution': execution,
            '_eventId': 'submit'
        }
        res = self.sess.post(url=self.LOGIN_URL, data=data, headers=self.HEADERS)

        # check if login successfully
        if '统一身份认证' in res.content.decode():
            raise LoginError('登录失败，请核实账号密码重新登录')
        return self.sess

    def post(self):
        """Post the hitcard info"""
        res = self.sess.post(self.SAVE_URL, data=self.info, headers=self.HEADERS)
        return json.loads(res.text)

    def get_date(self):
        """Get current date"""
        today = datetime.date.today()
        return "%4d%02d%02d" % (today.year, today.month, today.day)

#     def get_captcha(self):
#         """Get CAPTCHA code"""
#         resp = self.sess.get(self.CAPTCHA_URL)
#         captcha = self.ocr.classification(resp.content)
#         print("验证码：", captcha)
#         return captcha

    def get_info(self, html=None):
        """Get hitcard info, which is the old info with updated new time."""
        if not html:
            res = self.sess.get(self.BASE_URL, headers=self.HEADERS)
            html = res.content.decode()

        try:
            old_infos = re.findall(r'oldInfo: ({[^\n]+})', html)
            if len(old_infos) != 0:
                old_info = json.loads(old_infos[0])
            else:
                raise RegexMatchError("未发现缓存信息，请先至少手动成功打卡一次再运行脚本")

            new_info_tmp = json.loads(re.findall(r'def = ({[^\n]+})', html)[0])
            new_id = new_info_tmp['id']
            name = re.findall(r'realname: "([^\"]+)",', html)[0]
            number = re.findall(r"number: '([^\']+)',", html)[0]
        except IndexError:
            raise RegexMatchError('Relative info not found in html with regex')
        except json.decoder.JSONDecodeError:
            raise DecodeError('JSON decode error')

        new_info = old_info.copy()
        new_info['id'] = new_id
        new_info['name'] = name
        new_info['number'] = number
        new_info["date"] = self.get_date()
        new_info["created"] = round(time.time())
        new_info["address"] = "浙江省杭州市西湖区"
        new_info["area"] = "浙江省 杭州市 西湖区"
        new_info["province"] = new_info["area"].split(' ')[0]
        new_info["city"] = new_info["area"].split(' ')[1]
        # form change
        new_info['jrdqtlqk[]'] = 0
        new_info['jrdqjcqk[]'] = 0
        new_info['sfsqhzjkk'] = 1   # 是否申领杭州健康码
        new_info['sqhzjkkys'] = 1   # 杭州健康吗颜色，1:绿色 2:红色 3:黄色
        new_info['sfqrxxss'] = 1    # 是否确认信息属实
        new_info['jcqzrq'] = ""
        new_info['gwszdd'] = ""
        new_info['szgjcs'] = ""
        
        # 2022.05.07
        # new_info['verifyCode'] = self.get_captcha() # 验证码识别（已取消）
        
        # 2022.07.05
        new_info['internship'] = 3  # 今日是否进行实习或实践

        # 2021.08.05 Fix 2
        magics = re.findall(r'"([0-9a-f]{32})":\s*"([^\"]+)"', html)
        for item in magics:
            new_info[item[0]] = item[1]

        self.info = new_info
        return new_info

    def _rsa_encrypt(self, password_str, e_str, M_str):
        password_bytes = bytes(password_str, 'ascii')
        password_int = int.from_bytes(password_bytes, 'big')
        e_int = int(e_str, 16)
        M_int = int(M_str, 16)
        result_int = pow(password_int, e_int, M_int)
        return hex(result_int)[2:].rjust(128, '0')
    
#     @staticmethod
#     def md5(str):
#         import hashlib
#         m = hashlib.md5()
#         m.update(str.encode("utf8"))
#         return m.hexdigest()

#     def  send_sms(self, phone_num, content):
#         smsapi = "http://api.smsbao.com/"
#         # 短信平台账号, 如果你需要可以在smsbao.com自己注册一个
#         user = 'stdbay'
#         # 短信平台密码, 这里是用的是我自己的，你也可以换成自己的
#         password = ClockIn.md5('d7ae96be97a44fcd8f4a767fd438737b')
        
#         print('开始发送短信...')
#         data = urllib.parse.urlencode({'u': user, 'p': password, 'm': phone_num, 'c': content})
#         send_url = smsapi + 'sms?' + data
#         response = urllib.request.urlopen(send_url)
#         the_page = response.read().decode('utf-8')
#         print (statusStr[the_page])

    def send_e_mail(self, mail_addr, token, content):
        # 第三方 SMTP 服务
        mail_host="smtp.qq.com"  #设置服务器，不同供应商的地址不一样
        mail_pass=token   #口令

        sender = mail_addr
        receivers = [mail_addr]  # 调用自己的SMTP服务，通常的邮件服务商如QQ邮箱，Gmail都会提供该功能
        
        # 三个参数：第一个为文本内容，第二个 plain 设置文本格式，第三个 utf-8 设置编码
        message = MIMEText(content, 'plain', 'utf-8')
        message['From'] = Header("ZJU自动打卡脚本", 'utf-8')   # 发送者
        message['To'] =  Header("使用者", 'utf-8')        # 接收者
        
        subject = '【自动打卡通知】'
        message['Subject'] = Header(subject, 'utf-8')
        try:
            print('开始发送邮件')
            smtpObj = smtplib.SMTP() 
            smtpObj.connect(mail_host, 25)    # 25 为 SMTP 端口号
            smtpObj.login(mail_addr, mail_pass)
            smtpObj.sendmail(sender, receivers, message.as_string())
            print("邮件发送成功")
        except smtplib.SMTPException as e:
            print("发送邮件失败, 错误信息: ")
            print(e.strerror)


# Exceptions
class LoginError(Exception):
    """Login Exception"""
    pass


class RegexMatchError(Exception):
    """Regex Matching Exception"""
    pass


class DecodeError(Exception):
    """JSON Decode Exception"""
    pass


def main(username, password, email, token, phone):
    """Hit card process
    Arguments:
        username: (str) 浙大统一认证平台用户名（一般为学号）
        password: (str) 浙大统一认证平台密码
    """
    print(username, password, email, token, phone)
    print("\n[Time] %s" %
          datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    print("🚌 打卡任务启动")
    
    dk = ClockIn(username, password)
    
    print("登录到浙大统一身份认证平台...")
    try:
        dk.login()
        print("已登录到浙大统一身份认证平台")
    except Exception as err:
        print('登录失败, 更多信息: ')
        print(str(err))
        raise Exception

    print('正在获取个人信息...')
    try:
        dk.get_info()
        print('已成功获取个人信息')
    except Exception as err:
        print('获取信息失败，请手动打卡，更多信息: ' + str(err))
        raise Exception

    print('正在为您打卡')
    try:
        res = dk.post()
        if str(res['e']) == '0':
            print('已为您打卡成功！')
#             if len(phone) > 0:
#                 dk.send_sms(phone, dk.content_ok)
            if len(email) == 0 and len(token) == 0:
                dk.send_e_mail(email, token, dk.content_ok)
            
        else:
            print(res['m'])
            if res['m'].find("已经") != -1: # 已经填报过了 不报错
                pass
            elif res['m'].find("验证码错误") != -1: # 验证码错误
                print('再次尝试')
                time.sleep(5)
                main(username, password)
                pass
            else:
                raise Exception
    except Exception:
        print('数据提交失败')
#         if len(phone) > 0:
#             dk.send_sms(phone, dk.content_fail)
        if len(email) == 0 and len(token) == 0:
            dk.send_e_mail(email, token, dk.content_fail)
        raise Exception


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='获取配置参数')
    parser.add_argument("--account", default=' 22221057', help='ZJU学号')
    parser.add_argument("--password", default=' hzwhw2000414', help='ZJU密码')
    parser.add_argument("--email", default=' 1224342775@qq.com', help='邮件地址')
    parser.add_argument("--token", default=' swignrphbewogiba', help='邮件口令')
    parser.add_argument("--phone", default=' 15156053994', help='电话号码')
    args = parser.parse_args()
    
    try:
        # 此处去掉开头的占位符
        main(args.account[1:], args.password[1:], args.email[1:], args.token[1:], args.phone[1:])
    except Exception as e:
        exit(1)
