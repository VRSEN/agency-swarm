import paramiko
import select
import time

class SSHCommandExecutor:
    def __init__(self,hostname,username,password,port = 22,timeout=10):
        self.client = paramiko.SSHClient()
        self.hostname = hostname
        self.port = port
        self.username = username
        self.password = password
        self.timeout = timeout
        self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        self._is_connected = False  # Track connection state

    def connect(self):
        if self._is_connected:
            return True
        try:
            print(f"\n[DEBUG]正在连接到{self.hostname}:{self.port}...")
            self.client.connect(self.hostname, port=self.port, username=self.username, password=self.password, timeout=self.timeout)
            print(f"\n[DEBUG]成功连接到 {self.hostname}:{self.port}.")
            self._is_connected = True
            return True
        except paramiko.AuthenticationException:
            print("\n[DEBUG]Authentication failed: Invalid username or password.")
            self.close()
            return False
        except paramiko.SSHException as e:
            print(f"\n[DEBUG]SSH connection error: {e}")
            self.close()
            return False
        except Exception as e:
            print(f"\n[DEBUG]An unknown error occurred during connection: {e}")
            self.close()
            return False


    def execute_command_stream(self, command, buffer_size=4096):
        if not self._is_connected:
            if not self.connect():  # Attempt to connect, and check if it was successful
                yield '__error__', "Failed to connect to SSH server."
                return  # If connection fails, stop execution
        stdout_data_full = []
        stderr_data_full = []
        exit_status = None
        try:
            stdin, stdout, stderr = self.client.exec_command(command)
            channel = stdout.channel
            channel.settimeout(1.0)  # 设置通道的超时时间
            while True:
                rlist, _, _ = select.select([channel], [], [], 0.1)
                if channel in rlist:
                    # 读取stdout
                    if channel.recv_ready():
                        data = channel.recv(buffer_size).decode('utf-8', errors='ignore')
                        if data:
                            stdout_data_full.append(data)  # 收集所有数据
                            yield 'stdout', data  # 实时产出
                            # print(f"STDOUT: {data}", end='')

                    # 读取stderr
                    if channel.recv_stderr_ready():
                        data = channel.recv_stderr(buffer_size).decode('utf-8', errors='ignore')
                        if data:
                            stderr_data_full.append(data)  # 收集所有数据
                            yield 'stderr', data  # 实时产出
                            # print(f"STDERR: {data}", end='')

                # 检查命令是否完成
                if channel.exit_status_ready():
                    exit_status = channel.recv_exit_status()
                    break  # 命令完成，退出循环

                # 如果没有数据可读且命令未完成，等待一小段时间
                # 这个判断可以防止在命令执行过程中CPU空转过快
                if not stdout_data_full and not stderr_data_full and \
                        not channel.recv_ready() and not channel.recv_stderr_ready() and \
                        not channel.exit_status_ready():
                    time.sleep(0.05)

            print(f"\n[DEBUG]命令 '{command}' 执行完成。")
            # 最后再追加一个结果，包含stdout，stderr和exit_status
            yield '__final_status__', "".join(stdout_data_full), "".join(stderr_data_full), exit_status

        except Exception as e:
            print(f"发生未知错误：{e}")
            yield '__error__', f"An unknown error occurred: {e}"

    def execute_command_common(self, command, buffer_size=4096):
        full_stdout = []
        full_stderr = []
        final_status = None

        # 调用生成器函数
        data_generator = self.execute_command_stream(command, buffer_size)
        try:
            for data_type, *data_content in data_generator:
                if data_type == 'stdout':
                    full_stdout.append(data_content[0])
                elif data_type == 'stderr':
                    full_stderr.append(data_content[0])
                elif data_type == '__final_status__':
                    # 获取最终结果
                    full_stdout_str, full_stderr_str, final_status = data_content
                    # 此时已经获取到最终结果，可以选择跳出循环，或者让生成器自然耗尽
                    break
                elif data_type == '__error__':
                    print(f"操作发生错误: {data_content[0]}")
                    final_status = -1  # 表示一个客户端错误
                    break
        except Exception as e:
            print(f"处理生成器输出时发生异常: {e}")
            final_status = -2  # 表示一个处理错误
        return {"full_stdout": ' '.join(full_stdout), "full_stderr": ' '.join(full_stderr), "final_status": final_status}


    def close(self):
        """
        Closes the SSH connection.
        """
        if self.client:
            self.client.close()
            print(f"Connection to {self.hostname}:{self.port} closed.")
            self.client = None

        self.client = paramiko.SSHClient()  # 重置client，以便后续可以重新连接
        self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())


if __name__ == "__main__":
    # 请替换为您的SSH服务器信息
    HOSTNAME = "127.0.0.1"  # 例如: "192.168.1.100"
    PORT = 8022
    USERNAME = "tommenx"  # 例如: "user"x
    PASSWORD = "test"  # 例如: "your_secret_password"

    exec = SSHCommandExecutor(HOSTNAME, USERNAME, PASSWORD,port=PORT)
    exec.connect()
    # # --- 测试用例 ---
    # run_test_command(exec,"echo 'Hello from SSH (yield)!'")
    # run_test_command(exec,"ls -l /")
    # run_test_command(exec,"this_command_does_not_exist_123")
    # run_test_command(exec,"cat /etc/shadow")  # 权限拒绝
    # run_test_command(exec,"for i in $(seq 1 3); do echo 'Line $i (yield)'; sleep 1; done")  # 长时间运行
    # run_test_command(exec,"echo 'This will go to STDERR' >&2; exit 1")  # 命令直接输出到stderr并退出
    # def run_test_command_stream(cmd, buffer_size=4096):
    #     data_generator = exec.execute_command_stream(cmd)
    #     for data_type, *data_content in data_generator:
    #         if data_type == 'stdout':
    #             print(f"stdout{data_content[0]}")
    #         elif data_type == 'stderr':
    #             print(f"stderr{data_content[0]}")
    #         elif data_type == '__final_status__':
    #             # 获取最终结果
    #             full_stdout_str, full_stderr_str, final_status = data_content
    #             # 此时已经获取到最终结果，可以选择跳出循环，或者让生成器自然耗尽
    #             break
    #         elif data_type == '__error__':
    #             print(f"操作发生错误: {data_content[0]}")
    #             final_status = -1  # 表示一个客户端错误
    #             break
    # run_test_command_stream("for i in $(seq 1 3); do echo 'Line $i (yield)'; sleep 1; done")

    # res = exec.execute_command_common("echo 'Hello from SSH (yield)!'")
    # print(res)
    # res = exec.execute_command_common("ls -l /")
    # print(res)
    # res = exec.execute_command_common("this_command_does_not_exist_123")
    # print(res)
    # res = exec.execute_command_common("cat /etc/shadow")
    # print(res)
    res = exec.execute_command_common("for i in $(seq 1 3); do echo 'Line $i (yield)'; sleep 1; done")
    print(res)
