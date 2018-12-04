import socket
import threading
import struct

IP = '127.0.0.1'
PORT = 1613

# 定义数据长度 
# 一个数据包的数据为 1024 bytes
# 再加上 24 bytes 的序列号，确认号，文件结束标志
_BUFFER_SIZE = 1024 + 24

# 传送包的结构定义
# 使用 python 的 struct 定义
# 包括 序列号，确认号，文件结束标志，1024B的数据
# pkt_value = (int seq, int ack, int end_flag 1024B的byte类型 data)
pkt_struct = struct.Struct('III1024s')

# 信息反馈包
fb_struct = struct.Struct('II')


def receiver(s, cli_address, file_name):
    print('服务器正在接受', file_name, '从客户端', cli_address)

    # 文件暂存
    # 模式wb 以二进制格式打开一个文件只用于写入。
    # 如果该文件已存在则打开文件，并从开头开始编辑，即原有内容会被删除。
    # 如果该文件不存在，创建新文件。
    f = open(file_name, 'wb')

    # 记录包的数目
    packet_count = 1

    # 将 rwnd 设置为 110
    rwnd = 110

    # 数据缓存
    temp_data = []

    while True:
        # 读传输的数据 data
        data, cli_address = s.recvfrom(_BUFFER_SIZE)
        # 提取包数据
        try:
            unpkt_data = pkt_struct.unpack(data)
        except struct.error as e:
            break
        
        packet_count += 1

        if rwnd > 0:
            # 若序列号为0，也就是 seq 为零，跳过该包
            if unpkt_data[0] == 0:
                s.sendto(fb_struct.pack(*(unpkt_data[0], rwnd)), cli_address)
                continue

            # 如果序号不连续，丢弃该包
            if unpkt_data[1] != packet_count - 1:
                print('包序号错误！-> ', unpkt_data[0])
                # 发回上一个包
                s.sendto(fb_struct.pack(*(unpkt_data[1] - 1, rwnd)), sev_address)
                continue

            temp_data.append(unpkt_data)
            rwnd -= 1
            # 接收完毕，返回 ACK
            s.sendto(fb_struct.pack(*(unpkt_data[0], rwnd)), cli_address)
        # 缓冲不足
        else:
            s.sendto(fb_struct.pack(*(unpkt_data[0], rwnd)), cli_address)
        
        print('服务器已经接受第',unpkt_data[0],'个包')

        # 文件写入
        while len(temp_data) > 0:
            unpkt_data = temp_data[0]
            seq = unpkt_data[0]
            ack = unpkt_data[1]
            end = unpkt_data[2]
            data = unpkt_data[3]
            
            # 读取数据后删除，然后缓冲空间 +1 s
            del temp_data[0]
            rwnd += 1

            # 写入数据，直到 end = 1
            if end != 1:
                f.write(data)
            else:
                break
        
        if unpkt_data[2] == 1:
            break

        print('传输完毕'+str(packet_count), '个包')
        
        # 保存关闭文件
        f.close


def server_child_thread(data, cli_address):
    # 对传输过来的 data 进行处理
    # data 的内容为 ‘命令, 文件名’
    # 提取命令以及文件名
    try:
        command = data.decode('utf-8').split(',')[0]
        file_name = data.decode('utf-8').split(',')[1]
    except Exception as e:
        return

    # 建立 socket 链接
    # socket.SOCK_DGRAM -> 基于UDP的数据报式socket通信
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    # 设置 socket 缓冲区
    # 待定
    s.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 1024 * 64)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 1024 * 64)


    if command == 'lsend':
        s.sendto('发起链接？'.encode('utf-8'), cli_address)
        # 等待客户端确认
        # data?
        data, cli_address = s.recvfrom(_BUFFER_SIZE)
        print('来自', cli_address,'的数据是：', data.decode('utf-8'))
        receiver(s, cli_address, file_name)

    print('\n开始断开连接（四次握手）')

    data, sev_address = s.recvfrom(_BUFFER_SIZE)
    print(data.decode('utf-8'))

    data = '我服务器同意断开连接'
    s.sendto(data.encode('utf-8'), cli_address)
    print(data)

    data = '我服务器请求断开连接'
    s.sendto(data.encode('utf-8'), cli_address)
    print(data)

    data, sev_address = s.recvfrom(_BUFFER_SIZE)
    print(data.decode('utf-8'))

    print('结束链接')
    s.close()




def main():
    # 建立 socket 链接
    # socket.SOCK_DGRAM -> 基于UDP的数据报式socket通信
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    # 将套接字绑定到地址
    s.bind((IP, PORT))

    while True:
        # 客户端会先发送操作指令以及客户端IP过来
        data, cli_address = s.recvfrom(_BUFFER_SIZE)

        # 每当请求来，便开启一个线程
        # 线程执行的函数为 server_child_thread
        # args 表示函数参数
        child_thread = threading.Thread(target=server_child_thread, args=(data, cli_address))
        # 启动
        child_thread.start()

if __name__ == "__main__":
    main()