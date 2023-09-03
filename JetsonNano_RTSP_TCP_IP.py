import sys
import threading
import gi
from socket import *
import sys
import time
import RPi.GPIO as GPIO
from PCA9685 import PCA9685

pwm = PCA9685()
pwm.setPWMFreq(50)
HOST = '192.168.0.48'  # 현재 Jetson nano의 ipv4주소 
PORT = 8888

def send(sock):
	while True:
		sendData = input('>>>')
		sock.send(sendData.encode('utf-8'))

# PC로부터 SERVO CONTROL 신호를 수신하면 Jetson nano와 연결된 servo motor를 제어함.
def receive(sock):
	while True:
		recvData = sock.recv(1024)
		print('수신 :', recvData.decode('utf-8'))
		angle = int(recvData.decode('utf-8'))
		if angle % 2 == 1 :
			pwm.setRotationAngle(1, int(angle/10))   #x축
		else :
			pwm.setRotationAngle(0, int(angle/10))   #y축

# GStreamer 라이브러리는 c로 작성되었으므로 우선 c언어와 python간 바인딩 작업을 수행함.
# GStreamer의 최소 버전을 PyGObject에 알림.
gi.require_version('Gst', '1.0')

# 'Gst','GLib'모듈을 사용하기 위해 임포트.
from gi.repository import Gst, GLib, GstRtspServer
from threading import Thread

# 'GLib'메인 루프를 스레드에서 동작하도록 함. 
main_loop = GLib.MainLoop()
GLib.threads_init()
Gst.init()

#Jetson nano와 연결된 CSI카메라를 사용하기 위해서 파이프라인의 소스, 영상 압축방식, 스트리밍 설정 등 을 설정함
class MyFactory(GstRtspServer.RTSPMediaFactory):
	def __init__(self):
		GstRtspServer.RTSPMediaFactory.__init__(self)

	def do_create_element(self, url):
		s_src = "nvarguscamerasrc sensor-id=0 ! video/x-raw(memory:NVMM),width=1920, height=1080, format=(string)NV12, framerate=60/1"
		s_h264 = "nvv4l2h264enc insert-sps-pps=true maxperf-enable=1 bitrate=8000000 ! h264parse"
		#s_h264 = "nvvidconv ! x264enc tune=zerolatency byte-stream=true ! h264parse config-interval=1"
	
		pipeline_str = "( {s_src} ! queue name=q_enc ! {s_h264} ! rtph264pay name=pay0 pt=96 )".format(**locals())
		if len(sys.argv) > 1:
			pipeline_str = " ".join(sys.argv[1:])
		print(pipeline_str)
		return Gst.parse_launch(pipeline_str)

# Jetson nano에서 RTSP프로토콜로 CSI카메라의 영상을 스트리밍하기 위한 서버 설정작업. 
class GstServer():
	def __init__(self):
		self.server = GstRtspServer.RTSPServer()
		self.server.set_service("8554")
		f = MyFactory()
		f.set_shared(True)
		m = self.server.get_mount_points()
		m.add_factory("/gaonnuri", f)
		self.server.attach(None)

# RTSP스트리밍 시작. 
rtsp = GstServer()
print("RTSP 서버 설정 완료")
thread = Thread(target=main_loop.run)
thread.start()
print("RTSP 스트리밍 시작. 주소 : rtsp://" + HOST + "/"+ "8554" + "/gaonnuri")

#TCP/IP 통신 시작.
s = socket(AF_INET, SOCK_STREAM)
s.bind((HOST, PORT))
s.listen(1)
print('%d번 포트 접속 대기중...'%PORT)

connectionSock, addr = s.accept()
print(str(addr), '에서 접속됨.')

# PC와 Jetson nano 간 TCP/IP통신에서 데이터를 수신하는 작업을 스레드로 동작함. 
#sender = threading.Thread(target=send, args=(connectionSock,))
receiver = threading.Thread(target=receive, args=(connectionSock,))

#sender.start()
receiver.start()

try:
	while 1:
		time.sleep(1)
except KeyboardInterrupt:
	pass
rtsp.set_state(Gst.State.NULL)	
main_loop.quit()
