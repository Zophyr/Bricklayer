import re
import os
import socket
import time
import struct

PORT = 1613

# 定义数据长度 
# 一个数据包的数据为 1024 bytes
# 再加上 24 bytes 的序列号，确认号，文件结束标志
_BUFFER_SIZE = 1024 + 24

# 定义每次读取文件长度 
# 1024 bytes
_FILE_SIZE = 1024

# 传送包的结构定义
# 使用 python 的 struct 定义
# 包括 序列号，确认号，文件结束标志，1024B的数据
# pkt_value = (int seq, int ack, int end_flag 1024B的byte类型 data)
pkt_struct = struct.Struct('III1024s')

# 信息反馈包
fb_struct = struct.Struct('II')

def sender(s, sev_address, file_name):
    # 首先确认链接
    # 发送 ACK
    data = 'ACK'.encode('utf-8')
    s.sendto(data, sev_address)

    # 文件打开
    # 模式rb 以二进制格式打开一个文件用于只读。
    # 文件指针将会放在文件的开头。
    f = open(file_name, 'rb')
    
    # 记录包的数目
    packet_count = 1
    # 下一个要传的包的序号 seq
    next_packet = 1

    # 判断 rwnd 是否为 0
    IS_RWND_ZERO = False
    
    # 判断时候需要重传
    IS_RESEND = False

    # 判断时候拥塞
    IS_OVERSIZE = False

    # 判断是否线性增长
    IS_LINEAR = False

    # 将窗口初始化为 1
    cwnd = 1

    # 数据缓存
    temp_data = []

    # 初始化拥塞阈值 win_size 为 30
    win_size = 30

    # 缓存上一个发送的包，用于重传
    temp_pkt = ['LFTP']

    while True:
        seq = packet_count
        ack = packet_count

        if IS_OVERSIZE == True:
            print('堵车， 恢复cwnd：', cwnd)
            time.sleep(0.01613)
            continue

        if IS_RWND_ZERO == False:
            if IS_RESEND == False:
                data = f.read(_FILE_SIZE)

                # 阻塞控制
                # 当未到阈值，指数增长
                if cwnd < win_size and IS_LINEAR == False:
                    cwnd *= 2
                # 若到达阈值，值线性增长
                else:
                    cwnd += 1
                    IS_LINEAR = True
            # 重新传输
            else:
                seq -= 1
                ack -= 1
                packet_count -= 1
                print('重新传输 seq =', seq)
                data = temp_pkt[0]
                # 更新新的阈值
                temp = cwnd
                cwnd = win_size
                win_size = int(temp / 2) + 1

            del temp_pkt[0]

            # 暂存传输的包
            temp_pkt.append(data)
            next_packet = seq

            # 若文件没有传输完成
            if str(data) != "b''":
                end = 0
                s.sendto(pkt_struct.pack(*(seq, ack, end, data)), sev_address)

            # 文件传输完成
            else:
                end = 1
                data = 'end'.encode('utf-8')
                packet_count += 1
                s.sendto(pkt_struct.pack(*(seq, ack, end, data)), sev_address)

                # 等待服务器响应 ACK
                # ?
                pkt_data, pkt_address = s.recvfrom(_BUFFER_SIZE)
                unpkt_data = fb_struct.unpack(pkt_data)
                
                ack = unpkt_data[0]
                rwnd = unpkt_data[1]
                
                print('接收服务器：', pkt_address, 'ack: ', ack)
                
                break

        else:
            if IS_RESEND == False:
                seq = 0
                end = 0
                data = 'rwnd'.encode('utf-8')
            else:
                seq -= 1
                ack -= 1
                packet_count -= 1
                data = temp_pkt[0]
            
            del temp_pkt[0]
            
            # 暂存传输的包
            temp_pkt.append(data)
            next_packet = seq

            s.sendto(pkt_struct.pack(*(seq, ack, end, data)), sev_address)

        packet_count += 1
        
        # 等待服务器响应 ACK
        # ?
        pkt_data, pkt_address = s.recvfrom(_BUFFER_SIZE)
        unpkt_data = fb_struct.unpack(pkt_data)
                
        ack = unpkt_data[0]
        rwnd = unpkt_data[1]

        # 判断时候需要重新传送
        if rwnd == 0:
            IS_RESEND = True
        else:
            IS_RESEND = False

        print('接收服务器：', pkt_address, 'ack: ', ack)
    
    print('传输完毕'+str(packet_count), '个包')
        
    # 保存关闭文件
    f.close


def main():
    # 读取命令行输入交互
    command = input('输入格式：操作 服务器地址 文件名。 eg. lsend 127.0.0.1 client.py\n')

    # 正则匹配读取
    pattern = re.compile(r'(lsend|lget) (\S+) (\S+)')

    match = pattern.match(command)

    if command:
        command = match.group(1)
        sev_ip = match.group(2)
        file_name = match.group(3)
    else:
        print('输入错误，请重输。eg. lsend 127.0.0.1 client.py')

    # 判断文件是否存在
    if command == 'lsend' and (os.path.exists(file_name) is False):
        print(file_name, '文件不存在！')
        exit(0)

    # 建立 socket 链接
    # socket.SOCK_DGRAM -> 基于UDP的数据报式socket通信
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    # 设置 socket 缓冲区
    # 待定
    s.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 1024 * 64)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 1024 * 64)

    # 处理将要发送给服务器的 data
    # data 的内容为 ‘命令, 文件名’
    data = (command+','+file_name).encode('utf-8')
    sev_address=(sev_ip, PORT)

    # 建立连接
    s.sendto(data, sev_address)

    # 接收返回的数据
    data, sev_address = s.recvfrom(_BUFFER_SIZE)
    print('服务器', sev_address, '说', data.decode('utf-8'))

    if command == 'lsend':
        sender(s, sev_address, file_name)

    print('\n开始断开连接（四次握手）')

    data = '我客户端请求断开连接'
    s.sendto(data.encode('utf-8'), sev_address)
    print(data)

    data, cli_address = s.recvfrom(_BUFFER_SIZE)
    print(data.decode('utf-8'))

    data, cli_address = s.recvfrom(_BUFFER_SIZE)
    print(data.decode('utf-8'))

    data = '我客户端同意断开连接'
    s.sendto(data.encode('utf-8'), sev_address)
    print(data)

    print('结束链接')
    s.close()

if __name__ == "__main__":
    main()
